/******************************************************************************
 * MSP430FR2355 - NTC Thermistor Temperature Measurement
 *
 * Adds temperature conversion to the ADC reading from Part 1.
 * Uses the Beta equation for the NTC0805J10K thermistor.
 *
 * Thermistor Parameters (NTC0805J10K, TE Connectivity / Neohm):
 *   R0   = 10,000 Ω  (resistance at 25°C)
 *   Beta = 3435 K     (B25/50 constant)
 *   T0   = 298.15 K   (25°C in Kelvin)
 *
 * Voltage Divider:
 *   Vout = Vcc × R_therm / (R_fixed + R_therm)
 *   Solving: R_therm = R_fixed × ADC_raw / (4095 - ADC_raw)
 ******************************************************************************/

#include <msp430.h>
#include <stdint.h>
#include <math.h>         // For log() and 1/x — link with -lm if needed

// ---- Thermistor & Circuit Constants ----
// CURRENTLY NOT USED BUT KEEPING FOR REFERENCE 
#define R_FIXED     10000.0f    // Fixed resistor in voltage divider (Ω)
#define R0_NTC      10000.0f    // NTC resistance at 25°C (Ω)
#define BETA        3435.0f     // Beta constant B25/50 (K)
#define T0_KELVIN   298.15f     // 25°C in Kelvin
#define ADC_MAX     4095.0f     // 12-bit ADC maximum value

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
//    ADC    T×10     R_th        Verify: ADC/4095 ratio
    {  585, 800 },  //  80.0°C   R= 1,665Ω   0.143
    {  740, 700 },  //  70.0°C   R= 2,206Ω   0.181
    {  940, 600 },  //  60.0°C   R= 2,981Ω   0.230
    { 1192, 500 },  //  50.0°C   R= 4,107Ω   0.291
    { 1495, 400 },  //  40.0°C   R= 5,751Ω   0.365
    { 1668, 350 },  //  35.0°C   R= 6,874Ω   0.407
    { 1854, 300 },  //  30.0°C   R= 8,278Ω   0.453
    { 2048, 250 },  //  25.0°C   R=10,000Ω   0.500  ← VCC/2 ✓
    { 2247, 200 },  //  20.0°C   R=12,163Ω   0.549
    { 2450, 150 },  //  15.0°C   R=14,895Ω   0.598
    { 2655, 100 },  //  10.0°C   R=18,432Ω   0.648
    { 2850,  50 },  //   5.0°C   R=22,884Ω   0.696
    { 3037,   0 },  //   0.0°C   R=28,700Ω   0.742
    { 3210, -50 },  //  -5.0°C   R=36,260Ω   0.784
    { 3367,-100 },  // -10.0°C   R=46,280Ω   0.822
    { 3507,-150 },  // -15.0°C   R=59,660Ω   0.856
    { 3627,-200 },  // -20.0°C   R=77,450Ω   0.886
};

#define LUT_SIZE (sizeof(lut) / sizeof(lut[0]))

void main(void)
{
    WDTCTL = WDTPW | WDTHOLD;          // Stop watchdog timer

    P1SEL0 &= ~BIT3;
    P1SEL1 &= ~BIT3;
    P1DIR  |=  BIT3;
    P1OUT  &= ~BIT3;

    // Configure P1.0 as analog input (A0)
    P1SEL0 |= BIT0;
    P1SEL1 |= BIT0;
    
    PM5CTL0 &= ~LOCKLPM5;              // Unlock GPIO

    __delay_cycles(10000);

    init_ADC();

    while (1)
    {
        P1OUT &= ~BIT3;

        adc_raw = read_ADC();

        __delay_cycles(100000);         // ~100ms delay

        // Convert to temperature
        temperature_C_x10 = adc_to_temperature_x10(adc_raw);
        temperature_F_x10 = (temperature_C_x10 * 9 / 5) + 320;

        __no_operation();

        __delay_cycles(100000);         // ~100ms delay
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
    while (!(ADCIFG & ADCIFG0));
    //__delay_cycles(100);
    ADCIFG &= ~ADCIFG0;
    ADCCTL0 &= ~ADCENC;
    return ADCMEM0;
}

int16_t adc_to_temperature_x10(uint16_t adc_val)
{
    uint16_t i;

    // Clamp to table range
    if (adc_val <= lut[0].adc)
        return lut[0].temp_x10;                 // Above 80°C

    if (adc_val >= lut[LUT_SIZE - 1].adc)
        return lut[LUT_SIZE - 1].temp_x10;      // Below -20°C

    // Find the two table entries that bracket our ADC value
    // Table is sorted: low ADC = hot, high ADC = cold
    for (i = 0; i < LUT_SIZE - 1; i++)
    {
        if (adc_val >= lut[i].adc && adc_val <= lut[i + 1].adc)
        {
            // =============================================
            // Linear interpolation between two table entries
            //
            // Given:
            //   adc_val is between lut[i].adc and lut[i+1].adc
            //   We want the temperature between lut[i].temp and lut[i+1].temp
            //
            //         (adc_val - adc_lo)
            // T = T_hi - ──────────────── × (T_hi - T_lo)
            //           (adc_hi - adc_lo)
            //
            // Note: "hi" temp = lut[i] (lower ADC = hotter)
            // =============================================
            uint16_t adc_lo  = lut[i].adc;
            uint16_t adc_hi  = lut[i + 1].adc;
            int16_t  temp_hi = lut[i].temp_x10;      // Higher temp
            int16_t  temp_lo = lut[i + 1].temp_x10;  // Lower temp

            int32_t numerator   = (int32_t)(adc_val - adc_lo) * (temp_hi - temp_lo);
            int16_t denominator = (int16_t)(adc_hi - adc_lo);

            return temp_hi - (int16_t)(numerator / denominator);
        }
    }

    return 0;   // Should never reach here
}
