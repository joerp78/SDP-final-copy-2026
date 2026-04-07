#include <msp430.h>
#include <stdint.h>
#include "em4325_spi.h"

// -----------------------
// Your pin mapping
// SCLK = P1.5 (UCA0CLK)
// MISO = P1.6 (UCA0SOMI)
// MOSI = P1.7 (UCA0SIMO)
// CS   = P2.0 (GPIO)
// -----------------------
#define EM_CS_DIR   P2DIR
#define EM_CS_OUT   P2OUT
#define EM_CS_PIN   BIT0

static inline void CS_LOW(void)  { EM_CS_OUT &= ~EM_CS_PIN; }
static inline void CS_HIGH(void) { EM_CS_OUT |=  EM_CS_PIN; }

// quick CS-high gap between commands (datasheet wants a small gap)
static void delay_us_approx(unsigned int us)
{
    // crude delay; good enough for command spacing
    while (us--) { __delay_cycles(1); }
}

static uint8_t spi_txrx(uint8_t b)
{
    while (!(UCA0IFG & UCTXIFG)) {}
    UCA0TXBUF = b;
    while (!(UCA0IFG & UCRXIFG)) {}
    return UCA0RXBUF;
}

// EM4325 replies after some dummy clocks; reply begins with a '1' bit.
// We treat "MSB=1" as "reply started" and return that first reply byte (status).
static uint8_t wait_status_byte(void)
{
    unsigned int i;
    for (i = 0; i < 64; i++)
    {
        uint8_t r = spi_txrx(0x00);
        if (r & 0x80) return r;
    }
    return 0x00;
}

void EM4325_SPI_Init(void)
{
    // CS as GPIO output, inactive high
    EM_CS_DIR |= EM_CS_PIN;
    CS_HIGH();

    // Put SPI pins into eUSCI_A0 peripheral function
    // For FR2355: typically SEL0=1, SEL1=0 selects primary module function
    P1SEL0 |=  (BIT5 | BIT6 | BIT7);
    P1SEL1 &= ~(BIT5 | BIT6 | BIT7);

    // Configure eUSCI_A0 for SPI master, 3-wire, MSB first
    UCA0CTLW0 |= UCSWRST;  // hold in reset

    // NOTE: SPI mode can be tuned if needed.
    // This setting (UCCKPH=1, UCCKPL=0) works as a common default on MSP430.
    UCA0CTLW0 = UCSWRST
              | UCSSEL__SMCLK
              | UCMST
              | UCSYNC
              | UCMSB
              | UCCKPH;     // try this first; if readback fails, we can flip UCCKPH

    // SPI clock divider: SMCLK / 4 (conservative)
    UCA0BRW = 4;

    UCA0CTLW0 &= ~UCSWRST; // release reset
}

uint8_t EM4325_WriteWord(uint8_t wordAddr, uint16_t dataWord)
{
    CS_LOW();

    spi_txrx(EM4325_CMD_SPI_WRITE_WORD);
    spi_txrx(wordAddr);

    // Send data MSB first
    spi_txrx((uint8_t)(dataWord >> 8));
    spi_txrx((uint8_t)(dataWord & 0xFF));

    // Dummy clocks until status appears
    uint8_t status = wait_status_byte();

    CS_HIGH();
    delay_us_approx(20);

    return status;
}

uint8_t EM4325_ReadWord(uint8_t wordAddr, uint16_t *outWord)
{
    if (!outWord) return 0;

    CS_LOW();

    spi_txrx(EM4325_CMD_SPI_READ_WORD);
    spi_txrx(wordAddr);

    // Dummy clocks until status appears
    uint8_t status = wait_status_byte();

    // Then read 16-bit data
    uint8_t msb = spi_txrx(0x00);
    uint8_t lsb = spi_txrx(0x00);

    CS_HIGH();
    delay_us_approx(20);

    *outWord = ((uint16_t)msb << 8) | lsb;
    return status;
}
