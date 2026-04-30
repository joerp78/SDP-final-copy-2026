/*******************************************************************************
 * main.c — MSP430FR2355 — DAC sine-wave generation foundation
 *
 * DAC output:  SAC3 buffer on P3.5, 10 kHz sine wave (16 samples/cycle)
 * Temperature: NTC on P1.0 (A0), conversion helpers retained for later use
 * RFID:        EM4325 SPI driver retained for later use
 * Sensors:     P1.3 enables TPS22917 load switch (SENS_VDD rail)
 * MUX:         P5.3=EN, P5.1=A1, P5.0=A0 — enabled for future probe use
 ******************************************************************************/

#include <msp430.h>
#include <stdint.h>
#include "em4325_spi.h" // hello

/* ---- Sine generation config ----
 * MCLK = SMCLK = 8 MHz
 * Samples per sine period = 16
 * Target sine frequency = 10 kHz
 * Update frequency = 10k * 16 = 160 kHz
 * Timer period counts = 8,000,000 / 160,000 = 50 counts -> CCR0 = 49
 */
#define SINE_SAMPLES         (16U)
#define SINE_TIMER_CCR0      (49U)
#define ADC_CAPTURE_SAMPLES  (160U)
#define ADC_CAPTURE_CCR0     (649U)
#define EM4325_USER_WORD2_ADDR  (EM4325_USER_WORD0_ADDR + 2U)
#define MEASUREMENT_SETTLE_CYCLES (16000U)
#define CONDUCTIVITY_AIR_RAW     (51U)
#define CONDUCTIVITY_WATER_RAW   (4094U)
#define PHASE_VALID_MIN_PKPK_RAW (8U)
#define ADC_RAIL_LOW_THRESHOLD   (16U)
#define ADC_RAIL_HIGH_THRESHOLD  (4079U)
#define FEEDBACK_RETURN_HIGH_PKPK_RAW (200U)
#define FEEDBACK_RETURN_HIGH_COUNT    (3U)
#define TAG_PHASE_INVALID_WORD        (0x8000U)
#define DAC_LUT_CENTER_RAW            (2048)
#define DAC_LUT_PKPK_RAW              (4094U)
#define TAG_PHASE_VALID_BIT           (0x8000U)

/* ---- EM4325 USER payload format ----
 * USER word 0:
 *   Raw temperature ADC count (unsigned 16-bit) from
 *   P1.0 / ADC channel A0.
 *
 * USER word 1:
 *   Raw phase packet.
 *   Bit 15 = phase-valid flag:
 *     1 -> phase valid
 *     0 -> phase invalid / not enough signal
 *   Bits [11:0] = signed phase delay in deg_x10, two's complement.
 *     Example: 123 = +12.3 deg, 0xFF85 = -12.3 deg in 12-bit two's complement.
 *
 * USER word 2:
 *   Raw conductivity amplitude packet.
 *   Bit 15 = feedback state during export:
 *     0 -> P2.4 high (high sensitivity path)
 *     1 -> P2.4 low  (reduced gain / anti-rail path)
 *   Bits [11:0] = raw conductivity amplitude
 *     (I/Q-derived amplitude, scaled to ADC-count-like peak-to-peak units).
 *
 * Server-side decode:
 *   temp_raw = word0
 *   phase_valid = (word1 & 0x8000) != 0
 *   phase_raw_12 = word1 & 0x0FFF
 *   if (phase_raw_12 & 0x0800) phase_raw_12 -= 0x1000
 *   phase_deg = phase_raw_12 / 10.0
 *   feedback_low = (word2 & 0x8000) != 0
 *   conductivity_raw = word2 & 0x0FFF
 */

/* ---- Globals ---- */
volatile uint16_t adc_temp_raw      = 0;
volatile int16_t  temperature_C_x10 = 0;
volatile int16_t  temperature_F_x10 = 0;
volatile uint8_t  sine_index        = 0;
volatile uint16_t adc_probe_raw     = 0;
volatile uint16_t adc_probe_mV      = 0;
volatile uint32_t adc_probe_count   = 0;
volatile uint16_t adc_capture_buffer[160] = {0};
volatile uint8_t  adc_capture_phase_idx[160] = {0};
volatile uint16_t adc_capture_index       = 0;
volatile uint16_t adc_capture_min_raw     = 0x0FFF;
volatile uint16_t adc_capture_max_raw     = 0;
volatile uint16_t adc_capture_pkpk_raw    = 0;
volatile uint16_t adc_capture_done        = 0;
volatile uint16_t adc_capture_mean_raw    = 0;
volatile uint16_t adc_capture_mean_mV     = 0;
volatile uint16_t adc_capture_avgdev_raw  = 0;
volatile uint16_t adc_capture_avgdev_mV   = 0;
volatile uint16_t moisture_signal_raw     = 0;
volatile uint16_t moisture_signal_mV      = 0;
volatile uint32_t moisture_capture_count  = 0;
volatile uint32_t temperature_update_count = 0;
volatile uint8_t  em4325_temp_write_status = 0;
volatile uint8_t  em4325_phase_write_status = 0;
volatile uint8_t  rfid_write_triggered      = 0;
volatile uint16_t temperature_tag_word     = 0;
volatile uint16_t phase_tag_word           = TAG_PHASE_INVALID_WORD;
volatile uint16_t conductivity_tag_word    = 0;
volatile uint8_t  em4325_cond_write_status = 0;
volatile uint8_t  feedback_low_enabled     = 0;
volatile uint8_t  adc_capture_railed       = 0;
volatile uint32_t feedback_switch_count    = 0;
volatile uint8_t  feedback_high_return_count = 0;
volatile uint16_t adc_phase_bins_raw[SINE_SAMPLES] = {0};
volatile uint16_t adc_phase_bins_count[SINE_SAMPLES] = {0};
volatile uint8_t  phase_delay_steps       = 0;
volatile uint16_t phase_delay_deg_x10     = 0;
volatile uint16_t phase_delay_steps_x100  = 0;
volatile uint16_t phase_delay_deg_x100    = 0;
volatile int16_t  phase_delay_signed_steps_x100 = 0;
volatile int16_t  phase_delay_signed_deg_x10    = 0;
volatile int16_t  phase_delay_us_x100           = 0;
volatile int32_t  phase_delay_ns                = 0;
volatile uint8_t  phase_delay_valid             = 0;
volatile int32_t  phase_correlation_score = 0;
volatile int32_t  iq_in_phase_raw        = 0;
volatile int32_t  iq_quadrature_raw      = 0;
volatile uint32_t iq_magnitude_raw       = 0;

/* ---- Prototypes ---- */
void     init_Clock_8MHz(void);
void     init_GPIO(void);
void     init_ADC(void);
uint16_t read_ADC_channel(uint16_t input_channel);
void     init_DAC(void);
void     init_Sine_Timer_10kHz_16samples(void);
void     init_ADC_Capture_Timer(void);
void     process_ADC_Capture(void);
void     reset_ADC_Capture(void);
int16_t  adc_to_temperature_x10(uint16_t adc_val);
void     update_raw_export_words(void);
void     set_feedback_low(void);
void     set_feedback_high(void);
uint32_t isqrt_u64(uint64_t value);
int16_t  approx_atan2_deg_x10(int32_t y, int32_t x);
static void peripherals_shutdown(void);
static void peripherals_wakeup(void); 

/* 12-bit DAC LUT, centered at midscale (2048), full-scale-ish swing */
static const uint16_t sine_lut_16[SINE_SAMPLES] = {
    2048, 2831, 3496, 3939,
    4095, 3939, 3496, 2831,
    2048, 1265,  600,  157,
       1,  157,  600, 1265
};

/* ---- Temperature LUT ----
 * ADC vs temp for 10k NTC + 10k fixed divider, 12-bit, AVCC ref
 * Sorted ascending ADC (descending temperature)                  */
typedef struct {
    uint16_t adc;
    int16_t  temp_x10;
} TempLookup_t;

static const TempLookup_t lut[] = {
    {  585,  800 },   //  80.0 C
    {  740,  700 },   //  70.0 C
    {  940,  600 },   //  60.0 C
    { 1192,  500 },   //  50.0 C
    { 1495,  400 },   //  40.0 C
    { 1668,  350 },   //  35.0 C
    { 1854,  300 },   //  30.0 C
    { 2048,  250 },   //  25.0 C  (NTC = R_fixed, half supply)
    { 2247,  200 },   //  20.0 C
    { 2450,  150 },   //  15.0 C
    { 2655,  100 },   //  10.0 C
    { 2850,   50 },   //   5.0 C
    { 3037,    0 },   //   0.0 C
    { 3210,  -50 },   //  -5.0 C
    { 3367, -100 },   // -10.0 C
    { 3507, -150 },   // -15.0 C
    { 3627, -200 },   // -20.0 C
};
#define LUT_SIZE (sizeof(lut) / sizeof(lut[0]))

#pragma vector = PORT2_VECTOR
__interrupt void PORT2_ISR(void)
{
    if (P2IFG & BIT1)
    {
        P2IFG &= ~BIT1;              // clear the flag first
        rfid_write_triggered = 1U;   // signal main loop to write
        __bic_SR_register_on_exit(LPM3_bits); // wake CPU
    }
}


/* ===========================================================================
 *                              MAIN
 * =========================================================================== */
void main(void)
{
    WDTCTL = WDTPW | WDTHOLD; 

    init_Clock_8MHz();
    init_GPIO();
    PM5CTL0 &= ~LOCKLPM5;       // unlock pins
    P2IFG &= ~BIT1;    // clear any flag that set during unlock
    P2IE  |=  BIT1;
    __delay_cycles(80000);      // let SENS_VDD rail settle (~10ms @ 8MHz)

    init_DAC();
    init_Sine_Timer_10kHz_16samples();
    init_ADC();
    EM4325_SPI_Init();
    init_ADC_Capture_Timer();
    __bis_SR_register(GIE);     // enable global interrupts
    rfid_write_triggered = 1U;

    while (1)
    {
        if (adc_capture_done)
        {
            adc_capture_railed =
                ((adc_capture_min_raw <= ADC_RAIL_LOW_THRESHOLD) ||
                 (adc_capture_max_raw >= ADC_RAIL_HIGH_THRESHOLD)) ? 1U : 0U;

            if (adc_capture_railed && !feedback_low_enabled)
            {
                set_feedback_low();
                __delay_cycles(MEASUREMENT_SETTLE_CYCLES);
                reset_ADC_Capture();
                continue;
            }

            if (feedback_low_enabled)
            {
                if (adc_capture_railed)
                {
                    feedback_high_return_count = 0U;
                }
                else if (adc_capture_pkpk_raw <= FEEDBACK_RETURN_HIGH_PKPK_RAW)
                {
                    feedback_high_return_count++;
                    if (feedback_high_return_count >= FEEDBACK_RETURN_HIGH_COUNT)
                    {
                        set_feedback_high();
                        feedback_high_return_count = 0U;
                        __delay_cycles(MEASUREMENT_SETTLE_CYCLES);
                        reset_ADC_Capture();
                        continue;
                    }
                }
                else
                {
                    feedback_high_return_count = 0U;
                }
            }
            else
            {
                feedback_high_return_count = 0U;
            }

            process_ADC_Capture();

            adc_temp_raw = read_ADC_channel(ADCINCH_0);
            temperature_C_x10 = adc_to_temperature_x10(adc_temp_raw);
            temperature_F_x10 = (temperature_C_x10 * 9 / 5) + 320;
            update_raw_export_words();

            if (rfid_write_triggered)
            {
                em4325_temp_write_status =
                    EM4325_WriteWord(EM4325_USER_WORD0_ADDR,
                                     temperature_tag_word);
                em4325_phase_write_status =
                    EM4325_WriteWord(EM4325_USER_WORD0_ADDR + 1U,
                                     phase_tag_word);
                em4325_cond_write_status =
                    EM4325_WriteWord(EM4325_USER_WORD2_ADDR,
                                     conductivity_tag_word);
                temperature_update_count++;

                // Placeholder trigger behavior: perform one export, then wait
                // for future firmware to assert the trigger again.
                rfid_write_triggered = 0U;
            }

            reset_ADC_Capture();
            /*
            peripherals_shutdown();

            P2IFG &= ~BIT1;
            if (!rfid_write_triggered)
            {
                __bis_SR_register(LPM3_bits + GIE);
            }

            peripherals_wakeup();
            */ 
        }

        __no_operation();
    }
}

/* ===========================================================================
 *                          CLOCK (8 MHz DCO)
 * =========================================================================== */
void init_Clock_8MHz(void)
{
    uint16_t lock_timeout = 60000;

    CSCTL0_H = 0xA5;                         // unlock CS registers
    CSCTL1   = DCORSEL_3;                    // DCO = 8 MHz
    CSCTL4   = SELMS__DCOCLKDIV | SELA__REFOCLK; // MCLK/SMCLK=DCO, ACLK=REFO
    CSCTL5   = DIVM__1 | DIVS__1;            // MCLK = SMCLK = 8 MHz

    // Do not block forever if lock bits never clear on this silicon/session.
    while ((CSCTL7 & (FLLUNLOCK0 | FLLUNLOCK1)) && lock_timeout--)
        ;

    CSCTL0_H = 0x00;                         // lock CS registers
}


/* ===========================================================================
 *                          GPIO SETUP
 * =========================================================================== */
void init_GPIO(void)
{
    // P1.3 — SENSORS_ON (TPS22917 enable), start HIGH
    P1SEL0 &= ~BIT3;
    P1SEL1 &= ~BIT3;
    P1DIR  |=  BIT3;
    P1OUT  |=  BIT3;

    // P1.0 — analog input A0 (temperature NTC)
    P1SEL0 |= BIT0;
    P1SEL1 |= BIT0;

    // P1.1 — analog input A1 (probe, configured for future use)
    P1SEL0 |= BIT1;
    P1SEL1 |= BIT1;

    // P3.5 — SAC3 OA output (DAC buffer → PROBE_DAC)
    P3SEL0 |= BIT5;
    P3SEL1 |= BIT5;

    // P2.0 — EM4325 CS (GPIO, setup completed in SPI init)
    P2SEL0 &= ~BIT0;
    P2SEL1 &= ~BIT0;

    // P2.1 — EM4325 AUX input reserved for later wakeup work
    P2SEL0 &= ~BIT1;
    P2SEL1 &= ~BIT1;
    P2DIR  &= ~BIT1;          // input
    P2REN  |=  BIT1;          // enable pull resistor
    P2OUT  &= ~BIT1;          // pull DOWN (AUX idles low, pulses high)
    P2IES  &= ~BIT1;          // rising edge triggers interrupt
    P2IFG  &= ~BIT1;          // clear any stale flag before enabling
    P2IE   |=  BIT1;          // enable the interrupt

    // P2.4 — feedback resistor select, start HIGH for max sensitivity.
    // If the ADC rails, firmware will automatically switch this LOW.
    P2SEL0 &= ~BIT4;
    P2SEL1 &= ~BIT4;
    P2DIR  |=  BIT4;
    P2OUT  |=  BIT4;

    // MUX control: P5.3=EN, P5.1=A1, P5.0=A0
    P5SEL0 &= ~(BIT3 | BIT1 | BIT0);
    P5SEL1 &= ~(BIT3 | BIT1 | BIT0);
    P5DIR  |=  (BIT3 | BIT1 | BIT0);
    P5OUT  |=  (BIT3 | BIT0);   // EN=1, A0=1
    P5OUT  &= ~BIT1;            // A1=0  → selects S2A/S2B
}


/* ===========================================================================
 *                          ADC (12-bit, switchable A0/A1)
 * =========================================================================== */
void init_ADC(void)
{
    ADCCTL0 &= ~ADCENC;
    ADCCTL0  = ADCSHT_0 | ADCON;        // 4-cycle S&H, ADC on
    ADCCTL1  = ADCSHP;                   // sample timer mode
    ADCCTL2  = ADCRES_2;                 // 12-bit resolution
    ADCMCTL0 = ADCINCH_1 | ADCSREF_0;   // channel A1 (P1.1), ref = AVCC/AVSS
}

uint16_t read_ADC_channel(uint16_t input_channel)
{
    ADCCTL0 &= ~ADCENC;
    ADCMCTL0 = input_channel | ADCSREF_0;
    ADCCTL0 |= ADCENC | ADCSC;          // enable + start conversion
    while (!(ADCIFG & ADCIFG0));         // wait for completion
    ADCIFG  &= ~ADCIFG0;                // clear flag
    ADCCTL0 &= ~ADCENC;                 // disable (required before next config change)
    return ADCMEM0;
}


/* ===========================================================================
 *                    DAC (SAC3 + OA3 buffer → P3.5)
 * =========================================================================== */
void init_DAC(void)
{
    // DAC: AVCC reference, immediate load on write, enable
    SAC3DAC = DACSREF_0 | DACLSEL_0 | DACEN;

    // OA: positive mux → DAC, negative mux → feedback, enable OA
    SAC3OA = SACEN | NMUXEN | PMUXEN | PSEL_1 | NSEL_1 | OAEN;

    // PGA: unity-gain buffer mode
    SAC3PGA = MSEL_1;

    // Start at first LUT sample
    SAC3DAT = 2048;
}

/* ===========================================================================
 *                TIMER_B0 ISR trigger for DAC sine update
 * =========================================================================== */
void init_Sine_Timer_10kHz_16samples(void)
{
    TB0CTL   = TBSSEL__SMCLK | MC__STOP | TBCLR;  // SMCLK source, stopped while config
    TB0CCR0  = SINE_TIMER_CCR0;                   // 160 kHz update rate
    TB0CCTL0 = CCIE;                              // enable CCR0 interrupt
    TB0CTL   = TBSSEL__SMCLK | MC__UP | TBCLR;    // start in up mode
}

/* ===========================================================================
 *               TIMER_B1 trigger for coherent ADC waveform capture
 * =========================================================================== */
void init_ADC_Capture_Timer(void)
{
    /* 650 SMCLK cycles = 13 DAC update periods.
     * Because gcd(13, 16) = 1, the ADC still walks through all 16 DAC phases
     * over successive samples, while running a bit faster than before. */
    TB1CTL   = TBSSEL__SMCLK | MC__STOP | TBCLR;
    TB1CCR0  = ADC_CAPTURE_CCR0;
    TB1CCTL0 = CCIE;
    TB1CTL   = TBSSEL__SMCLK | MC__UP | TBCLR;
}

void process_ADC_Capture(void)
{
    uint16_t i;
    uint16_t phase;
    uint32_t sum = 0;
    uint32_t sum_abs_dev = 0;
    uint32_t phase_sum[SINE_SAMPLES] = {0};
    uint16_t phase_count[SINE_SAMPLES] = {0};
    uint32_t ref_energy = 0;
    int32_t  i_accum = 0;
    int32_t  q_accum = 0;
    uint32_t vector_magnitude;
    uint32_t amplitude_pkpk_raw;
    int16_t  phase_angle_deg_x10;
    int32_t  signed_steps_x100;
    int32_t  angle_plus_180_x10;

    for (i = 0; i < ADC_CAPTURE_SAMPLES; i++)
    {
        sum += adc_capture_buffer[i];
    }

    adc_capture_mean_raw = (uint16_t)(sum / ADC_CAPTURE_SAMPLES);
    adc_capture_mean_mV  = (uint16_t)(((uint32_t)adc_capture_mean_raw * 3000U) / 4095U);

    for (i = 0; i < ADC_CAPTURE_SAMPLES; i++)
    {
        if (adc_capture_buffer[i] >= adc_capture_mean_raw)
            sum_abs_dev += (uint32_t)(adc_capture_buffer[i] - adc_capture_mean_raw);
        else
            sum_abs_dev += (uint32_t)(adc_capture_mean_raw - adc_capture_buffer[i]);
    }

    adc_capture_avgdev_raw = (uint16_t)(sum_abs_dev / ADC_CAPTURE_SAMPLES);
    adc_capture_avgdev_mV  = (uint16_t)(((uint32_t)adc_capture_avgdev_raw * 3000U) / 4095U);

    for (i = 0; i < ADC_CAPTURE_SAMPLES; i++)
    {
        phase = adc_capture_phase_idx[i] & 0x0FU;
        phase_sum[phase] += adc_capture_buffer[i];
        phase_count[phase]++;
    }

    for (phase = 0; phase < SINE_SAMPLES; phase++)
    {
        if (phase_count[phase] != 0U)
            adc_phase_bins_raw[phase] = (uint16_t)(phase_sum[phase] / phase_count[phase]);
        else
            adc_phase_bins_raw[phase] = 0;
        adc_phase_bins_count[phase] = phase_count[phase];
    }

    for (phase = 0; phase < SINE_SAMPLES; phase++)
    {
        int32_t adc_ac = (int32_t)adc_phase_bins_raw[phase] - (int32_t)adc_capture_mean_raw;
        int32_t sin_ref = (int32_t)sine_lut_16[phase] - DAC_LUT_CENTER_RAW;
        int32_t cos_ref = (int32_t)sine_lut_16[(phase + (SINE_SAMPLES / 4U)) & 0x0FU] - DAC_LUT_CENTER_RAW;

        i_accum += adc_ac * sin_ref;
        q_accum += adc_ac * cos_ref;
        ref_energy += (uint32_t)(sin_ref * sin_ref);
    }

    iq_in_phase_raw = i_accum;
    iq_quadrature_raw = q_accum;
    vector_magnitude = isqrt_u64((((uint64_t)i_accum) * ((uint64_t)i_accum)) +
                                 (((uint64_t)q_accum) * ((uint64_t)q_accum)));
    iq_magnitude_raw = vector_magnitude;

    amplitude_pkpk_raw = 0U;
    if (ref_energy != 0U)
    {
        amplitude_pkpk_raw =
            (uint32_t)(((uint64_t)vector_magnitude * DAC_LUT_PKPK_RAW) / ref_energy);
    }
    if (amplitude_pkpk_raw > 0x0FFFU)
        amplitude_pkpk_raw = 0x0FFFU;

    phase_angle_deg_x10 = approx_atan2_deg_x10(q_accum, i_accum);
    angle_plus_180_x10 = (int32_t)phase_angle_deg_x10 + 1800L;
    if (angle_plus_180_x10 < 0L)
        angle_plus_180_x10 += 3600L;
    if (angle_plus_180_x10 >= 3600L)
        angle_plus_180_x10 -= 3600L;

    phase_delay_deg_x10 = (uint16_t)angle_plus_180_x10;
    phase_delay_steps = (uint8_t)((phase_delay_deg_x10 + 112U) / 225U) & 0x0FU;
    phase_delay_steps_x100 = (uint16_t)((phase_delay_deg_x10 * 100L) / 225L);
    phase_delay_deg_x100 = (uint16_t)(phase_delay_deg_x10 * 10U);
    signed_steps_x100 = ((int32_t)phase_angle_deg_x10 * 100L) / 225L;
    phase_delay_signed_steps_x100 = (int16_t)signed_steps_x100;
    phase_delay_signed_deg_x10    = phase_angle_deg_x10;
    phase_delay_us_x100           = (int16_t)((signed_steps_x100 * 625L) / 100L);
    phase_delay_ns                = (signed_steps_x100 * 6250L) / 100L;
    phase_delay_valid             = (amplitude_pkpk_raw >= PHASE_VALID_MIN_PKPK_RAW) ? 1U : 0U;
    phase_correlation_score       = vector_magnitude;

    // Use coherent I/Q magnitude, scaled back to approximate peak-to-peak counts.
    moisture_signal_raw = (uint16_t)amplitude_pkpk_raw;
    moisture_signal_mV  = (uint16_t)(((uint32_t)moisture_signal_raw * 3000U) / 4095U);
    moisture_capture_count++;
}

void reset_ADC_Capture(void)
{
    adc_capture_index    = 0;
    adc_capture_min_raw  = 0x0FFF;
    adc_capture_max_raw  = 0;
    adc_capture_pkpk_raw = 0;
    adc_capture_done     = 0;

    TB1CTL   = TBSSEL__SMCLK | MC__STOP | TBCLR;
    TB1CCTL0 = CCIE;
    TB1CTL   = TBSSEL__SMCLK | MC__UP | TBCLR;
}

uint32_t isqrt_u64(uint64_t value)
{
    uint64_t bit = (uint64_t)1 << 62;
    uint64_t result = 0;

    while (bit > value)
        bit >>= 2;

    while (bit != 0U)
    {
        if (value >= result + bit)
        {
            value -= result + bit;
            result = (result >> 1) + bit;
        }
        else
        {
            result >>= 1;
        }
        bit >>= 2;
    }

    return (uint32_t)result;
}

int16_t approx_atan2_deg_x10(int32_t y, int32_t x)
{
    int32_t abs_y;
    int32_t angle_deg_x10;

    if ((x == 0) && (y == 0))
        return 0;

    if (x == 0)
        return (y > 0) ? 900 : -900;

    abs_y = (y >= 0) ? y : -y;
    abs_y += 1;

    if (x >= 0)
    {
        angle_deg_x10 = 450L - (450L * (x - abs_y)) / (x + abs_y);
    }
    else
    {
        angle_deg_x10 = 1350L - (450L * (x + abs_y)) / (abs_y - x);
    }

    if (y < 0)
        angle_deg_x10 = -angle_deg_x10;

    return (int16_t)angle_deg_x10;
}

void update_raw_export_words(void)
{
    int16_t phase_clamped = phase_delay_signed_deg_x10;

    temperature_tag_word = adc_temp_raw;
    conductivity_tag_word = moisture_signal_raw & 0x0FFFU;
    if (feedback_low_enabled)
        conductivity_tag_word |= 0x8000U;

    if (phase_clamped > 2047)
        phase_clamped = 2047;
    if (phase_clamped < -2048)
        phase_clamped = -2048;

    phase_tag_word = ((uint16_t)phase_clamped) & 0x0FFFU;
    if (phase_delay_valid)
        phase_tag_word |= TAG_PHASE_VALID_BIT;
}

void set_feedback_low(void)
{
    if (!feedback_low_enabled)
    {
        P2OUT &= ~BIT4;
        feedback_low_enabled = 1U;
        feedback_switch_count++;
        feedback_high_return_count = 0U;
    }
}

void set_feedback_high(void)
{
    if (feedback_low_enabled)
    {
        P2OUT |= BIT4;
        feedback_low_enabled = 0U;
        feedback_switch_count++;
        feedback_high_return_count = 0U;
    }
}

#pragma vector = TIMER0_B0_VECTOR
__interrupt void TIMER0_B0_ISR(void)
{
    SAC3DAT = sine_lut_16[sine_index];
    sine_index = (sine_index + 1U) & 0x0FU;
}

/* ---- Shutdown helpers ---- */
static void peripherals_shutdown(void)
{
    // Drive analog input pins low before cutting SENS_VDD
    // to prevent back-feed through ESD diodes
    P1SEL0 &= ~(BIT0 | BIT1);   // remove analog function
    P1SEL1 &= ~(BIT0 | BIT1);
    P1DIR  |=  (BIT0 | BIT1);   // set as output
    P1OUT  &= ~(BIT0 | BIT1);   // drive low

    // Same for P3.5 (DAC output / PROBE_DAC)
    P3SEL0 &= ~BIT5;
    P3SEL1 &= ~BIT5;
    P3DIR  |=  BIT5;
    P3OUT  &= ~BIT5;

    // Stop sine timer
    TB0CTL   = TBSSEL__SMCLK | MC__STOP | TBCLR;
    TB0CCTL0 &= ~CCIE;

    // Stop ADC capture timer
    TB1CTL   = TBSSEL__SMCLK | MC__STOP | TBCLR;
    TB1CCTL0 &= ~CCIE;

    // Disable DAC and OA
    SAC3OA  = 0;
    SAC3DAC = 0;

    // Put SPI in reset
    UCA0CTLW0 |= UCSWRST;

    // Drive all sensor-connected pins low
    P1SEL0 &= ~(BIT0 | BIT1 | BIT5 | BIT6 | BIT7);
    P1SEL1 &= ~(BIT0 | BIT1 | BIT5 | BIT6 | BIT7);
    P1DIR  |=  (BIT0 | BIT1 | BIT5 | BIT6 | BIT7);
    P1OUT  &= ~(BIT0 | BIT1 | BIT5 | BIT6 | BIT7);

    // Disable MUX
    P5OUT &= ~BIT3;

    // Cut SENS_VDD last
    P1OUT &= ~BIT3;

    __delay_cycles(80000);   // ~10ms at 8MHz
}

static void peripherals_wakeup(void)
{
    // 1. Restore SENS_VDD first
    P1OUT |= BIT3;
    __delay_cycles(80000);

    // 2. Restore SPI pins to eUSCI_A0 module function
    P1SEL0 |= (BIT5 | BIT6 | BIT7);
    P1SEL1 &= ~(BIT5 | BIT6 | BIT7);

    // 3. Restore analog input pins
    P1SEL0 |= (BIT0 | BIT1);
    P1SEL1 |= (BIT0 | BIT1);

    // 4. Restore P3.5 to SAC3 OA function
    P3SEL0 |= BIT5;
    P3SEL1 |= BIT5;

    // 5. Restore MUX enable
    P5OUT |= BIT3;

    // 6. Reinitialize peripherals
    init_DAC();
    init_Sine_Timer_10kHz_16samples();
    init_ADC();
    EM4325_SPI_Init();

    // 7. Reset capture state and restart capture timer
    adc_capture_index    = 0;
    adc_capture_min_raw  = 0x0FFF;
    adc_capture_max_raw  = 0;
    adc_capture_pkpk_raw = 0;
    adc_capture_done     = 0;
    init_ADC_Capture_Timer();

    // 8. Every wakeup is a reader event — always write this cycle
    rfid_write_triggered = 1U;
}

#pragma vector = TIMER1_B0_VECTOR
__interrupt void TIMER1_B0_ISR(void)
{
    uint16_t sample;
    uint8_t  phase_tag;

    if (adc_capture_done)
    {
        TB1CCTL0 &= ~CCIE;
        return;
    }

    phase_tag = sine_index;
    sample = read_ADC_channel(ADCINCH_1);
    adc_probe_raw = sample;
    adc_probe_mV  = (uint16_t)(((uint32_t)sample * 3000U) / 4095U);
    adc_probe_count++;

    adc_capture_buffer[adc_capture_index] = sample;
    adc_capture_phase_idx[adc_capture_index] = phase_tag;
    if (sample < adc_capture_min_raw)
        adc_capture_min_raw = sample;
    if (sample > adc_capture_max_raw)
        adc_capture_max_raw = sample;

    adc_capture_index++;
    if (adc_capture_index >= ADC_CAPTURE_SAMPLES)
    {
        adc_capture_pkpk_raw = adc_capture_max_raw - adc_capture_min_raw;
        adc_capture_done = 1;
        TB1CCTL0 &= ~CCIE;
    }
}


/* ===========================================================================
 *              TEMPERATURE CONVERSION (LUT + linear interpolation)
 * =========================================================================== */
int16_t adc_to_temperature_x10(uint16_t adc_val)
{
    // Clamp to table bounds
    if (adc_val <= lut[0].adc)
        return lut[0].temp_x10;
    if (adc_val >= lut[LUT_SIZE - 1].adc)
        return lut[LUT_SIZE - 1].temp_x10;

    // Find bracketing entries and interpolate
    uint16_t i;
    for (i = 0; i < LUT_SIZE - 1; i++)
    {
        if (adc_val >= lut[i].adc && adc_val <= lut[i + 1].adc)
        {
            uint16_t adc_lo  = lut[i].adc;
            uint16_t adc_hi  = lut[i + 1].adc;
            int16_t  temp_hi = lut[i].temp_x10;
            int16_t  temp_lo = lut[i + 1].temp_x10;

            int32_t num = (int32_t)(adc_val - adc_lo) * (temp_hi - temp_lo);
            int16_t den = (int16_t)(adc_hi - adc_lo);

            return temp_hi - (int16_t)(num / den);
        }
    }
    return 0;
}