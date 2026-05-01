/*******************************************************************************
 * em4325_spi.c
 *
 * Low-level SPI driver for the EM4325 RFID tag on the MSP430FR2355.
 *
 * SPI BUS OVERVIEW:
 *   The MSP430's eUSCI_A0 module is configured as a 3-wire SPI master:
 *     SCLK = P1.5   (clock, driven by MCU)
 *     MOSI = P1.7   (master-out / slave-in, driven by MCU)
 *     MISO = P1.6   (master-in / slave-out, driven by EM4325)
 *     CS   = P2.0   (chip select, active-low, GPIO bit-banged by MCU)
 *
 * PROTOCOL QUIRKS:
 *   The EM4325 does NOT respond immediately after a command.  After we
 *   send the command + address (+ data for writes), we must clock out
 *   dummy bytes (0x00) until the EM4325 begins its reply.  The start of
 *   the reply is signalled by the MSB of a received byte being '1'.
 *   We call this the "status byte."
 ******************************************************************************/

#include <msp430.h>
#include <stdint.h>
#include "em4325_spi.h"

/* ---- Chip-select pin definitions (active-low) ---- */
#define EM_CS_DIR   P2DIR
#define EM_CS_OUT   P2OUT
#define EM_CS_PIN   BIT0

#define EM4325_STATUS_WAIT_READ_BYTES   (32U)
#define EM4325_STATUS_WAIT_WRITE_BYTES  (512U)
#define EM4325_STATUS_WAIT_PAGE_BYTES   (512U)

/* Inline helpers — the compiler will replace these with single-instruction
 * bit-set / bit-clear on the port register (very fast, no function-call
 * overhead).                                                                */
static inline void CS_LOW(void)  { EM_CS_OUT &= ~EM_CS_PIN; }  /* Select   */
static inline void CS_HIGH(void) { EM_CS_OUT |=  EM_CS_PIN; }  /* Deselect */

/* ---- Short inter-command delay ----
 * The main firmware runs the MSP430 at 8 MHz, so one microsecond is about
 * 8 CPU cycles. Keep a small CS-high gap between transactions so the EM4325
 * can reliably separate back-to-back SPI commands.                         */
static void delay_us_approx(unsigned int us)
{
    while (us--)
    {
        __delay_cycles(8);
    }
}

/* ---- SPI single-byte transmit / receive ----
 *
 * Full-duplex: we load one byte into the TX buffer and simultaneously
 * receive one byte from the slave.
 *
 * How it works under the hood:
 *   1. Wait until the TX buffer is empty (UCTXIFG).
 *   2. Write the byte — this starts clocking 8 bits out on MOSI while
 *      simultaneously clocking 8 bits in on MISO.
 *   3. Wait until the RX buffer is full (UCRXIFG) — the transfer is done.
 *   4. Read and return the received byte.                                   */
static uint8_t spi_txrx(uint8_t byte_out)
{
    while (!(UCA0IFG & UCTXIFG))    /* 1. Wait for TX buffer empty          */
        ;
    UCA0TXBUF = byte_out;           /* 2. Start the transfer                */
    while (!(UCA0IFG & UCRXIFG))    /* 3. Wait for RX buffer full           */
        ;
    return UCA0RXBUF;               /* 4. Return the received byte          */
}

/* ---- Wait for the EM4325 status byte ----
 *
 * After a command, the EM4325's MISO line stays low (0x00) for a variable
 * number of clock bytes while it processes.  When it's ready, it sends a
 * byte with MSB=1.  We poll up to 64 dummy bytes; if no response appears,
 * we return 0x00 (failure / timeout).
 *
 * Why 64?  The EM4325 write latency is typically < 50 clock bytes; 64
 * gives comfortable margin without hanging forever on a wiring fault.       */
static uint8_t wait_status_byte(unsigned int attempts_max)
{
    unsigned int attempts;
    for (attempts = 0; attempts < attempts_max; attempts++)
    {
        uint8_t rx = spi_txrx(0x00);    /* Clock out dummy, read MISO      */
        if (rx & 0x80)                   /* MSB = 1 → reply has started     */
            return rx;                   /* Return the status byte          */
    }
    return 0x00;                         /* Timeout — no valid response     */
}

static uint8_t wait_ready_status(unsigned int polls_max)
{
    unsigned int poll;
    uint8_t status = 0U;

    for (poll = 0U; poll < polls_max; poll++)
    {
        status = EM4325_RequestStatus();
        if ((status & 0x80U) && ((status & 0x04U) == 0U))
            return status;
        delay_us_approx(100);
    }

    return status;
}


/* **************************************************************************
 * EM4325_SPI_Init() — one-time SPI bus setup
 * ************************************************************************** */

void EM4325_SPI_Init(void)
{
    /* 1. Configure the CS GPIO pin */
    EM_CS_DIR |= EM_CS_PIN;   /* P2.0 as output                            */
    CS_HIGH();                  /* Start deselected (CS = HIGH = inactive)   */

    /* 2. Route SPI signals to eUSCI_A0 pins.
     *    On the MSP430FR2355, the PRIMARY module function (SEL0=1, SEL1=0)
     *    maps these port pins to the eUSCI_A0 SPI signals:
     *      P1.5 → UCA0CLK   (SCLK)
     *      P1.6 → UCA0SOMI  (MISO, slave-out master-in)
     *      P1.7 → UCA0SIMO  (MOSI, slave-in master-out)                   */
    P1SEL0 |=  (BIT5 | BIT6 | BIT7);    /* SEL0 = 1 for all three          */
    P1SEL1 &= ~(BIT5 | BIT6 | BIT7);    /* SEL1 = 0 for all three          */

    /* 3. Configure eUSCI_A0 for SPI master mode.
     *
     *    First, assert the software reset (UCSWRST) — the module ignores
     *    all other register writes unless it's in reset.                    */
    UCA0CTLW0 |= UCSWRST;

    UCA0CTLW0 = UCSWRST            /* Keep reset asserted while we set up  */
              | UCSSEL__SMCLK       /* Clock source = SMCLK (8 MHz)        */
              | UCMST               /* Master mode (we drive SCLK)          */
              | UCSYNC              /* Synchronous mode = SPI (not UART)    */
              | UCMSB               /* MSB first (EM4325 protocol needs it) */
              | UCCKPH;             /* Clock phase: data captured on the
                                     * first SCLK edge, changed on the
                                     * second.  Combined with UCCKPL=0
                                     * (default), this is SPI "mode 0"
                                     * which works with the EM4325.
                                     * If reads return garbage, try
                                     * toggling UCCKPH.                     */

    /* 4. SPI clock divider.
     *    The main firmware runs SMCLK at 8 MHz, so use /32 to keep the
     *    EM4325 SPI clock at a conservative 250 kHz. This matches the timing
     *    assumptions used in bring-up and is much safer than accidentally
     *    running the tag interface at 2 MHz.                                */
    UCA0BRW = 32;

    /* 5. Release the software reset — the SPI module is now active
     *    and will clock data in/out whenever we write to UCA0TXBUF.        */
    UCA0CTLW0 &= ~UCSWRST;
}

uint8_t EM4325_RequestStatus(void)
{
    uint8_t status;

    CS_LOW();
    __delay_cycles(8);

    spi_txrx(EM4325_CMD_SPI_REQUEST_STATUS);
    status = wait_status_byte(EM4325_STATUS_WAIT_READ_BYTES);

    CS_HIGH();
    delay_us_approx(20);

    return status;
}

uint8_t EM4325_Reboot(void)
{
    uint8_t status;

    CS_LOW();
    __delay_cycles(8);

    spi_txrx(EM4325_CMD_SPI_BOOT);
    status = wait_status_byte(EM4325_STATUS_WAIT_READ_BYTES);

    CS_HIGH();
    delay_us_approx(100);

    if ((status & 0x80U) && (status & 0x04U))
        status = wait_ready_status(200U);

    return status;
}

uint8_t EM4325_SetTransponderEnabled(uint8_t enable)
{
    uint8_t status;

    CS_LOW();
    __delay_cycles(8);

    spi_txrx(enable ? EM4325_CMD_SPI_ENABLE_XPDR : EM4325_CMD_SPI_DISABLE_XPDR);
    status = wait_status_byte(EM4325_STATUS_WAIT_READ_BYTES);

    CS_HIGH();
    delay_us_approx(50);

    return status;
}


/* **************************************************************************
 * EM4325_WriteWord() — write a 16-bit word to EM4325 memory
 *
 * SPI frame on the wire:
 *
 *   CS LOW ─┐
 *            │  [CMD 0xE8] [ADDR] [DATA_MSB] [DATA_LSB] [dummy…] [STATUS]
 *   CS HIGH ┘
 *
 * We clock out the command, address, and 16-bit data, then poll for the
 * status byte.  The EM4325 writes to its internal EEPROM and replies
 * with a status byte (MSB=1) when the write completes.
 * ************************************************************************** */

uint8_t EM4325_WriteWord(uint8_t wordAddr, uint16_t dataWord)
{
    CS_LOW();                                   /* Begin SPI transaction    */
    __delay_cycles(8);                          /* Brief CS setup time      */

    spi_txrx(EM4325_CMD_SPI_WRITE_WORD);        /* 1. Send write command    */
    spi_txrx(wordAddr);                          /* 2. Send word address     */

    spi_txrx((uint8_t)(dataWord >> 8));          /* 3. Send data MSB        */
    spi_txrx((uint8_t)(dataWord & 0xFF));        /* 4. Send data LSB        */

    /* EM4325 writes are much slower than reads. At 250 kHz, one byte time is
     * about 32 us, so 512 dummy bytes gives about 16.4 ms of wait budget.
     * This safely covers the datasheet's worst-case SPIWriteWord time.      */
    uint8_t status = wait_status_byte(EM4325_STATUS_WAIT_WRITE_BYTES);

    CS_HIGH();                                   /* End SPI transaction      */
    delay_us_approx(20);                         /* Inter-command gap        */

    if ((status & 0x80U) && (status & 0x04U))
        status = wait_ready_status(200U);

    return status;
}


/* **************************************************************************
 * EM4325_ReadWord() — read a 16-bit word from EM4325 memory
 *
 * SPI frame on the wire:
 *
 *   CS LOW ─┐
 *            │  [CMD 0xE7] [ADDR] [dummy…] [STATUS] [MSB] [LSB]
 *   CS HIGH ┘
 *
 * After the status byte, we clock two more bytes to receive the 16-bit data.
 * ************************************************************************** */

uint8_t EM4325_ReadWord(uint8_t wordAddr, uint16_t *outWord)
{
    if (!outWord)                               /* Guard against null ptr   */
        return 0;

    CS_LOW();                                   /* Begin SPI transaction    */
    __delay_cycles(8);                          /* Brief CS setup time      */

    spi_txrx(EM4325_CMD_SPI_READ_WORD);          /* 1. Send read command     */
    spi_txrx(wordAddr);                           /* 2. Send word address     */

    /* Reads are much faster than writes; 32 dummy bytes gives about 1.0 ms at
     * 250 kHz, comfortably above the datasheet's max read processing time. */
    uint8_t status = wait_status_byte(EM4325_STATUS_WAIT_READ_BYTES);

    uint8_t msb = spi_txrx(0x00);                /* 4. Clock out data MSB    */
    uint8_t lsb = spi_txrx(0x00);                /* 5. Clock out data LSB    */

    CS_HIGH();                                    /* End SPI transaction      */
    delay_us_approx(20);                          /* Inter-command gap        */

    *outWord = ((uint16_t)msb << 8) | lsb;       /* 6. Assemble 16-bit word  */

    return status;
}

uint8_t EM4325_WritePage(uint8_t pageNum, const uint16_t *pageWords)
{
    uint8_t status;
    uint8_t i;

    if (!pageWords)
        return 0U;

    CS_LOW();
    __delay_cycles(8);

    spi_txrx(EM4325_CMD_SPI_WRITE_PAGE);
    spi_txrx((uint8_t)(pageNum & 0x7FU));

    for (i = 0U; i < 4U; i++)
    {
        spi_txrx((uint8_t)(pageWords[i] >> 8));
        spi_txrx((uint8_t)(pageWords[i] & 0xFFU));
    }

    status = wait_status_byte(EM4325_STATUS_WAIT_PAGE_BYTES);

    CS_HIGH();
    delay_us_approx(20);

    if ((status & 0x80U) && (status & 0x04U))
        status = wait_ready_status(200U);

    return status;
}

uint8_t EM4325_ReadPage(uint8_t pageNum, uint16_t *pageWords)
{
    uint8_t status;
    uint8_t i;
    uint8_t msb;
    uint8_t lsb;

    if (!pageWords)
        return 0U;

    CS_LOW();
    __delay_cycles(8);

    spi_txrx(EM4325_CMD_SPI_READ_PAGE);
    spi_txrx((uint8_t)(pageNum & 0x7FU));

    status = wait_status_byte(EM4325_STATUS_WAIT_READ_BYTES);

    for (i = 0U; i < 4U; i++)
    {
        msb = spi_txrx(0x00U);
        lsb = spi_txrx(0x00U);
        pageWords[i] = ((uint16_t)msb << 8) | lsb;
    }

    CS_HIGH();
    delay_us_approx(20);

    return status;
}
