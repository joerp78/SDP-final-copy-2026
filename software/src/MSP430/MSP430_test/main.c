#include <msp430.h>
#include <stdint.h>

volatile uint16_t sample_counter = 0;
volatile uint16_t temp_raw       = 0;

static void init_gpio(void);
static void init_adc(void);
static uint16_t read_adc_single(void);

int main(void)
{
    WDTCTL = WDTPW | WDTHOLD;          // Stop watchdog
    PM5CTL0 &= ~LOCKLPM5;              // Unlock GPIOs (FR devices power-up high-Z)

    init_gpio();
    init_adc();

    while (1)
    {
        temp_raw = read_adc_single();  // Blocking single conversion of P1.0 (A0)
        sample_counter++;              // Just so you can watch it in CCS

        __delay_cycles(1000000);       // ~1 s at default 1 MHz DCO
    }
}

static void init_gpio(void)
{
    // P1.3 drives the sensor enable pin low
    P1OUT &= ~BIT3;                    // Latch low before switching to output
    P1DIR |=  BIT3;
    P1SEL0 &= ~BIT3;
    P1SEL1 &= ~BIT3;

    // P1.0 as analog input A0
    P1SEL0 |= BIT0;
    P1SEL1 |= BIT0;
}

static void init_adc(void)
{
    ADCCTL0 &= ~ADCENC;                // Must clear ENC before configuring
    ADCCTL0 = ADCSHT_2 | ADCON;        // Sample&hold 16 ADC clocks, turn ADC on
    ADCCTL1 = ADCSHP;                  // Use sampling timer, single-channel single-conversion
    ADCCTL2 = ADCRES;                  // 12-bit resolution
    ADCMCTL0 = ADCINCH_0;              // Input channel A0, VR+ = AVCC, VR- = AVSS
    ADCCTL0 |= ADCENC;                 // Enable conversions
}

static uint16_t read_adc_single(void)
{
    ADCCTL0 |= ADCSC;                  // Start conversion
    while (ADCCTL1 & ADCBUSY);         // Wait until conversion completes
    return ADCMEM0;                    // Return the 12-bit result
}