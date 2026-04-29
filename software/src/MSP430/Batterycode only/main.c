#include <msp430.h>
#include <stdint.h>

// ---------------- BQ35100 ----------------
#define BQ35100_ADDR    0x55
#define BQ_CMD_VOLTAGE  0x08

// ---------------- Globals ----------------
volatile uint16_t batt_voltage_mV = 0;
volatile uint8_t  i2c_error = 0;

volatile uint16_t debug_P5OUT = 0;
volatile uint16_t debug_P5DIR = 0;

// ---------------- Prototypes ----------------
void init_clock_8MHz(void);
void init_gauge_enable(void);
void init_i2c_bq35100(void);
uint8_t bq_read_u16(uint8_t reg, uint16_t *value);

// ============================================================
// MAIN
// ============================================================
void main(void)
{
    WDTCTL = WDTPW | WDTHOLD;

    init_clock_8MHz();
    init_gauge_enable();

    PM5CTL0 &= ~LOCKLPM5;

    // Turn ON BQ35100
    P5OUT |= BIT2;

    // IMPORTANT: give it time to wake up
    __delay_cycles(8000000);   // ~1 second

    init_i2c_bq35100();

    while (1)
    {
        i2c_error = 0;

        // --- ONLY READ VOLTAGE ---
        if (bq_read_u16(BQ_CMD_VOLTAGE, &batt_voltage_mV) != 0)
        {
            i2c_error = 1;
        }

        // Debug GPIO state
        debug_P5OUT = P5OUT;
        debug_P5DIR = P5DIR;

        __no_operation();  // <- watch values here

        __delay_cycles(8000000);
    }
}

// ============================================================
// CLOCK
// ============================================================
void init_clock_8MHz(void)
{
    CSCTL0_H = 0xA5;
    CSCTL1   = DCORSEL_3;
    CSCTL4   = SELMS__DCOCLKDIV | SELA__REFOCLK;
    CSCTL5   = DIVM__1 | DIVS__1;
    CSCTL0_H = 0x00;
}

// ============================================================
// GAUGE ENABLE (P5.2)
// ============================================================
void init_gauge_enable(void)
{
    P5SEL0 &= ~BIT2;
    P5SEL1 &= ~BIT2;
    P5DIR  |=  BIT2;
    P5OUT  |=  BIT2;
}

// ============================================================
// I2C INIT (P4.6 SDA, P4.7 SCL)
// ============================================================
void init_i2c_bq35100(void)
{
    P4SEL0 |= BIT6 | BIT7;
    P4SEL1 &= ~(BIT6 | BIT7);

    UCB1CTLW0 = UCSWRST;

    UCB1CTLW0 |= UCMST | UCMODE_3 | UCSYNC | UCSSEL__SMCLK;

    UCB1BRW = 160;   // ~50 kHz (slower = more stable)

    UCB1I2CSA = BQ35100_ADDR;

    UCB1CTLW0 &= ~UCSWRST;
}

// ============================================================
// READ 16-bit REGISTER
// ============================================================
uint8_t bq_read_u16(uint8_t reg, uint16_t *value)
{
    uint8_t lsb, msb;
    uint16_t timeout;

    while (UCB1CTLW0 & UCTXSTP);

    UCB1I2CSA = BQ35100_ADDR;

    // Write register address
    UCB1CTLW0 |= UCTR | UCTXSTT;

    timeout = 60000;
    while (!(UCB1IFG & UCTXIFG0))
    {
        if (UCB1IFG & UCNACKIFG)
        {
            UCB1IFG &= ~UCNACKIFG;
            UCB1CTLW0 |= UCTXSTP;
            return 1;
        }
        if (--timeout == 0) return 2;
    }

    UCB1TXBUF = reg;

    timeout = 60000;
    while (!(UCB1IFG & UCTXIFG0))
    {
        if (--timeout == 0) return 3;
    }

    // Restart in RX mode
    UCB1CTLW0 &= ~UCTR;
    UCB1CTLW0 |= UCTXSTT;

    timeout = 60000;
    while (UCB1CTLW0 & UCTXSTT)
    {
        if (--timeout == 0) return 4;
    }

    // Read LSB
    timeout = 60000;
    while (!(UCB1IFG & UCRXIFG0))
    {
        if (--timeout == 0) return 5;
    }
    lsb = UCB1RXBUF;

    // Stop + read MSB
    UCB1CTLW0 |= UCTXSTP;

    timeout = 60000;
    while (!(UCB1IFG & UCRXIFG0))
    {
        if (--timeout == 0) return 6;
    }
    msb = UCB1RXBUF;

    while (UCB1CTLW0 & UCTXSTP);

    *value = ((uint16_t)msb << 8) | lsb;

    return 0;
}