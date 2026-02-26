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
#define R_FIXED     10000.0f    // Fixed resistor in voltage divider (Ω)
#define R0_NTC      10000.0f    // NTC resistance at 25°C (Ω)
#define BETA        3435.0f     // Beta constant B25/50 (K)
#define T0_KELVIN   298.15f     // 25°C in Kelvin
#define ADC_MAX     4095.0f     // 12-bit ADC maximum value

// ---- Global Variables ----
volatile uint16_t adc_raw = 0;
volatile float temperature_C = 0.0f;
volatile float temperature_F = 0.0f;

// ---- Function Prototypes ----
void init_ADC(void);
uint16_t read_ADC(void);
float adc_to_temperature_C(uint16_t adc_val);

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
        adc_raw = read_ADC();

        // Convert to temperature
        temperature_C = adc_to_temperature_C(adc_raw);
        temperature_F = (temperature_C * 9.0f / 5.0f) + 32.0f;

        __delay_cycles(100000);         // ~100ms delay
    }
}

/*---------------------------------------------------------------------------
 * init_ADC() — Same as Part 1
 *---------------------------------------------------------------------------*/
void init_ADC(void)
{
    ADCCTL0 = ADCSHT_2 | ADCON;
    ADCCTL1 = ADCSHP | ADCSSEL_2;
    ADCCTL2 = ADCRES_2;
    ADCMCTL0 = ADCINCH_0 | ADCSREF_0;
}

/*---------------------------------------------------------------------------
 * read_ADC() — Same as Part 1
 *---------------------------------------------------------------------------*/
uint16_t read_ADC(void)
{
    ADCCTL0 |= ADCENC | ADCSC;
    while (!(ADCIFG & ADCIFG0));
    ADCIFG &= ~ADCIFG0;
    ADCCTL0 &= ~ADCENC;
    return ADCMEM0;
}

/*---------------------------------------------------------------------------
 * adc_to_temperature_C()
 *
 * Converts a 12-bit ADC reading to temperature in °C.
 *
 * Step 1: ADC → Thermistor Resistance
 *   Since the thermistor is between the ADC pin and GND:
 *     Vout = Vcc × R_th / (R_fixed + R_th)
 *     ADC  = 4095 × R_th / (R_fixed + R_th)
 *   Solving for R_th:
 *     R_th = R_fixed × ADC / (4095 - ADC)
 *
 * Step 2: Resistance → Temperature (Beta Equation)
 *     1/T = 1/T0 + (1/Beta) × ln(R_th / R0)
 *     T(°C) = T(K) - 273.15
 *
 * Parameters:
 *   adc_val - raw 12-bit ADC reading (0–4095)
 *
 * Returns:
 *   Temperature in degrees Celsius (float)
 *---------------------------------------------------------------------------*/
float adc_to_temperature_C(uint16_t adc_val)
{
    float r_thermistor;
    float temp_kelvin;

    // Guard against division by zero
    if (adc_val >= 4095) adc_val = 4094;
    if (adc_val == 0) adc_val = 1;

    // Step 1: Calculate thermistor resistance from ADC value
    //   R_th = R_fixed × ADC / (4095 - ADC)
    r_thermistor = R_FIXED * ((float)adc_val / (ADC_MAX - (float)adc_val));

    // Step 2: Beta equation → Temperature in Kelvin
    //   1/T = 1/T0 + (1/B) × ln(R_th / R0)
    temp_kelvin = 1.0f / ((1.0f / T0_KELVIN) + (1.0f / BETA) * logf(r_thermistor / R0_NTC));

    // Step 3: Convert Kelvin → Celsius
    return temp_kelvin - 273.15f;
}