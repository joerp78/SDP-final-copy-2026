/******************************************************************************
 * MSP430FR2355 - NTC Thermistor Temperature Measurement + EM4325 SPI Relay
 *
 * - Reads thermistor via ADC (P1.0 / A0)
 * - Converts ADC to temperature (C x10, F x10)
 * - Writes temperature_C_x10 into EM4325 USER memory word 0 (addr 0x2C) via SPI
 *
 * SPI mapping (MSP430 -> EM4325):
 *   SCLK = P1.5 (UCA0CLK)
 *   MISO = P1.6 (UCA0SOMI)
 *   MOSI = P1.7 (UCA0SIMO)
 *   CS   = P2.0 (GPIO)
 ******************************************************************************/

#include <msp430.h>
#include <stdint.h>
#include <math.h>               // your project already used this
#include "src/em4325_spi.h"

// ---- Thermistor & Circuit Constants ----
// CURRENTLY NOT USED BUT KEEPING FOR REFERENCE
#define R_FIXED     10000.0f
#define R0_NTC      10000.0f
#define BETA        3435.0f
#define T0_KELVIN   298.15f
#define ADC_MAX     4095.0f

// ---- Global Variables ----
volatile uint16_t adc_raw = 0;
volatile int16_t temperature_C_x10 = 0;
volatile int16_t temperature_F_x10 = 0;

// ---- Function Prototypes ----
void init_ADC(void);
uint16_t read_ADC(void);
int16_t adc_to_temperature_x10(uint16_t adc_val);

typedef struct {
    uint16_t adc;
    int16_t  temp_x10;     // Temperature × 10
} TempLookup_t;

//  ADC values assume: R_fixed=10k, NTC R0=10k, B=3435, VCC ref
static const TempLookup_t lut[] = {
    {  585, 800 },  //  80.0°C
    {  740, 700 },  //  70.0°C
    {  940, 600 },  //  60.0°C
    { 1192, 500 },  //  50.0°C
    { 1495, 400 },  //  40.0°C
    { 1668, 350 },  //  35.0°C
    { 1854, 300 },  //  30.0°C
    { 2048, 250 },  //  25.0°C
    { 2247, 200 },  //  20.0°C
    { 2450, 150 },  //  15.0°C
    { 2655, 100 },  //  10.0°C
    { 2850,  50 },  //   5.0°C
    { 3037,   0 },  //   0.0°C
    { 3210, -50 },  //  -5.0°C
    { 3367,-100 },  // -10.0°C
    { 3507,-150 },  // -15.0°C
    { 3627,-200 },  // -20.0°C
};

#define LUT_SIZE (sizeof(lut) / sizeof(lut[0]))

void main(void)
{
    WDTCTL = WDTPW | WDTHOLD;          // Stop watchdog timer

    // P1.3 as GPIO output (you were using this as a pin toggle)
    P1SEL0 &= ~BIT3;
    P1SEL1 &= ~BIT3;
    P1DIR  |=  BIT3;
    P1OUT  &= ~BIT3;

    // Configure P1.0 as analog input (A0)
    P1SEL0 |= BIT0;
    P1SEL1 |= BIT0;

    // CS pin P2.0 must be GPIO (em4325 init will set it output/high)
    P2SEL0 &= ~BIT0;
    P2SEL1 &= ~BIT0;

    PM5CTL0 &= ~LOCKLPM5;              // Unlock GPIO
    __delay_cycles(10000);

    // Init peripherals
    init_ADC();
    EM4325_SPI_Init();

    while (1)
    {
        // Sample ADC
        adc_raw = read_ADC();

        __delay_cycles(100000);

        // Convert to temperature
        temperature_C_x10 = adc_to_temperature_x10(adc_raw);
        temperature_F_x10 = (temperature_C_x10 * 9 / 5) + 320;

        // Write temperature into EM4325 USER word 0 (addr 0x2C)
        // (stored as signed int16 in 2's complement)
        (void)EM4325_WriteWord(EM4325_USER_WORD0_ADDR, (uint16_t)temperature_C_x10);

        // Optional: readback for debug during bring-up
        // uint16_t rb = 0;
        // (void)EM4325_ReadWord(EM4325_USER_WORD0_ADDR, &rb);
        // __no_operation(); // set breakpoint and inspect rb

        __no_operation();
        __delay_cycles(100000);
    }
}

void init_ADC(void)
{
    ADCCTL0 &= ~ADCENC;
    ADCCTL0 = ADCSHT_2 | ADCON;
    ADCCTL1 = ADCSHP;
    ADCCTL2 = ADCRES_2;
    ADCMCTL0 = ADCINCH_0 | ADCSREF_0;
}

uint16_t read_ADC(void)
{
    ADCCTL0 |= ADCENC | ADCSC;
    while (!(ADCIFG & ADCIFG0)) {}
    ADCIFG &= ~ADCIFG0;
    ADCCTL0 &= ~ADCENC;
    return ADCMEM0;
}

int16_t adc_to_temperature_x10(uint16_t adc_val)
{
    // Clamp to table range
    if (adc_val <= lut[0].adc)
        return lut[0].temp_x10;

    if (adc_val >= lut[LUT_SIZE - 1].adc)
        return lut[LUT_SIZE - 1].temp_x10;

    // Find bracket and interpolate

    uint16_t i;
    for (i = 0; i < LUT_SIZE - 1; i++)
    {
        if (adc_val >= lut[i].adc && adc_val <= lut[i + 1].adc)
        {
            uint16_t adc_lo  = lut[i].adc;
            uint16_t adc_hi  = lut[i + 1].adc;
            int16_t  temp_hi = lut[i].temp_x10;
            int16_t  temp_lo = lut[i + 1].temp_x10;

            int32_t numerator   = (int32_t)(adc_val - adc_lo) * (temp_hi - temp_lo);
            int16_t denominator = (int16_t)(adc_hi - adc_lo);

            return temp_hi - (int16_t)(numerator / denominator);
        }
    }

    return 0;
}
