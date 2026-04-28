/*******************************************************************************
 * em4325_spi.h
 *
 * Driver interface for the EM4325 UHF RFID + sensor tag (EM Microelectronic).
 *
 * The EM4325 has an SPI slave interface that lets the host MCU read/write
 * its internal memory.  We use this to store sensor data (temperature,
 * moisture) into USER memory, which an external UHF RFID reader can then
 * retrieve wirelessly — no wires needed between the sensor node and the
 * base station.
 *
 * PHYSICAL CONNECTIONS (from schematic — ANTENNA page):
 *   MCU P1.5 (UCA0CLK)  → EM4325 pin 5  P2_SCLK
 *   MCU P1.6 (UCA0SOMI) → EM4325 pin 4  P1_MISO
 *   MCU P1.7 (UCA0SIMO) → EM4325 pin 3  P0_MOSI
 *   MCU P2.0 (GPIO)      → EM4325 pin 6  P3_CS   (active-low chip select)
 *   EM4325 VBAT (pin 7)  → VDD
 *   EM4325 VSS  (pin 8)  → GND
 *
 * MEMORY MAP (relevant portion):
 *   USER word 0 = physical word address 0x2C
 *   Each "word" is 16 bits.
 ******************************************************************************/

#ifndef EM4325_SPI_H_
#define EM4325_SPI_H_

#include <stdint.h>

/* ---- EM4325 SPI Command Opcodes (from EM4325 datasheet) ---- */
#define EM4325_CMD_SPI_READ_WORD    (0xE7)  /* Read a 16-bit word from memory  */
#define EM4325_CMD_SPI_WRITE_WORD   (0xE8)  /* Write a 16-bit word to memory   */

/* ---- USER Memory Base Address ---- */
#define EM4325_USER_WORD0_ADDR      (0x2C)  /* Physical address of USER word 0 */

/* ---- Public API ---- */

/**
 * EM4325_SPI_Init()
 *   Configures eUSCI_A0 as an SPI master (3-wire, MSB-first, ~250 kHz)
 *   and sets up the CS pin as a GPIO output (default HIGH / deselected).
 *   Call once after GPIO unlock.
 */
void EM4325_SPI_Init(void);

/**
 * EM4325_WriteWord()
 *   Writes one 16-bit word to the EM4325 memory at the given word address.
 *
 * @param  wordAddr   Physical word address (e.g. 0x2C for USER word 0)
 * @param  dataWord   16-bit data to write
 * @return            Status byte from the EM4325 (MSB=1 indicates valid reply)
 */
uint8_t EM4325_WriteWord(uint8_t wordAddr, uint16_t dataWord);

/**
 * EM4325_ReadWord()
 *   Reads one 16-bit word from the EM4325 memory at the given word address.
 *
 * @param  wordAddr   Physical word address
 * @param  outWord    Pointer to a uint16_t that receives the read data
 * @return            Status byte from the EM4325 (MSB=1 indicates valid reply)
 */
uint8_t EM4325_ReadWord(uint8_t wordAddr, uint16_t *outWord);

#endif /* EM4325_SPI_H_ */