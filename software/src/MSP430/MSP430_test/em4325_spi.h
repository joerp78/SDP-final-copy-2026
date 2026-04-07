#ifndef EM4325_SPI_H_
#define EM4325_SPI_H_

#include <stdint.h>

// EM4325 SPI commands (datasheet)
#define EM4325_CMD_SPI_READ_WORD    (0xE7)
#define EM4325_CMD_SPI_WRITE_WORD   (0xE8)

// USER memory physical word base address
// USER word 0 corresponds to physical word address 0x2C
#define EM4325_USER_WORD0_ADDR      (0x2C)

void     EM4325_SPI_Init(void);
uint8_t  EM4325_WriteWord(uint8_t wordAddr, uint16_t dataWord);
uint8_t  EM4325_ReadWord(uint8_t wordAddr, uint16_t *outWord);

#endif /* EM4325_SPI_H_ */
