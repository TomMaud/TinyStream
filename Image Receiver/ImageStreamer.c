#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "tusb.h"

#define SCREEN_WIDTH 135
#define SCREEN_HEIGHT 240
#define IMAGE_SIZE_BYTES (SCREEN_WIDTH * SCREEN_HEIGHT * 2) //Exactly 64,800 bytes

//Pin mapping matching your working script
#define PIN_DIN 19   //MOSI -> GP19
#define PIN_CLK 18   //SCK  -> GP18
#define PIN_CS  20   //CS   -> GP20
#define PIN_DC  16   //DC   -> GP16
#define PIN_RESET 17 //RES  -> GP17
#define PIN_BL  21   //BLK  -> GP21



//Exact working initialization sequence from your static test
static const uint8_t st7789_init_seq[] = {
    1, 30, 0x01, //Software reset
    1, 30, 0x11, //Exit sleep
    2, 0,  0x3a, 0x55, //Set colour mode
    2, 0,  0x36, 0x00, //Set MADCTL
    5, 0,  0x2a, 0x00, 52, 0x00, 52 + SCREEN_WIDTH - 1, //CASET
    5, 0,  0x2b, 0x00, 40, 0x01, (40 + SCREEN_HEIGHT - 1) & 0xff, //RASET
    1, 2,  0x21, //Inversion on
    1, 2,  0x13, //Normal display on
    1, 20, 0x29, //Main screen turn on
    0 //Terminate list
};

static inline void lcd_set_dc_cs(bool dc, bool cs) {
    sleep_us(1);
    gpio_put_masked((1u << PIN_DC) | (1u << PIN_CS), !!dc << PIN_DC | !!cs << PIN_CS);
    sleep_us(1);
}

static inline void lcd_write_cmd(const uint8_t *cmd, size_t count) {
    lcd_set_dc_cs(0, 0);
    spi_write_blocking(spi0, cmd++, 1);
    if (count >= 2) {
        lcd_set_dc_cs(1, 0);
        spi_write_blocking(spi0, cmd, count - 1);
    }
    lcd_set_dc_cs(1, 1);
}

static inline void lcd_init(const uint8_t *init_seq) {
    const uint8_t *cmd = init_seq;
    while (*cmd) {
        lcd_write_cmd(cmd + 2, *cmd);
        sleep_ms(*(cmd + 1) * 5);
        cmd += *cmd + 2;
    }
}

static inline void st7789_start_pixels() {
    uint8_t cmd = 0x2c; //RAMWR
    lcd_write_cmd(&cmd, 1);
    lcd_set_dc_cs(1, 0);
}


static inline void lcd_set_window() {
    uint8_t caset_payload[] = { 0x00, 52, 0x00, 52 + SCREEN_WIDTH - 1 };
    uint8_t raset_payload[] = { 0x00, 40, 0x01, (40 + SCREEN_HEIGHT - 1) & 0xff };
    uint8_t cmd_2a = 0x2a;
    uint8_t cmd_2b = 0x2b;
    
    lcd_set_dc_cs(0, 0);
    spi_write_blocking(spi0, &cmd_2a, 1);
    lcd_set_dc_cs(1, 0);
    spi_write_blocking(spi0, caset_payload, 4);

    lcd_set_dc_cs(0, 0);
    spi_write_blocking(spi0, &cmd_2b, 1);
    lcd_set_dc_cs(1, 0);
    spi_write_blocking(spi0, raset_payload, 4);
}

void lcd_clear(uint16_t color) {
    lcd_set_window();
    st7789_start_pixels();

    uint8_t color_bytes[2] = { (uint8_t)(color >> 8), (uint8_t)(color & 0xff) };
    for (int i = 0; i < SCREEN_WIDTH * SCREEN_HEIGHT; ++i) {
        spi_write_blocking(spi0, color_bytes, 2);
    }
    lcd_set_dc_cs(1, 1);
}

int main() {
    stdio_init_all(); 

    spi_init(spi0, 30 * 1000 * 1000);
    gpio_set_function(PIN_CLK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_DIN, GPIO_FUNC_SPI);

    gpio_init(PIN_CS);
    gpio_init(PIN_DC);
    gpio_init(PIN_RESET);
    gpio_init(PIN_BL);
    
    gpio_set_dir(PIN_CS, GPIO_OUT);
    gpio_set_dir(PIN_DC, GPIO_OUT);
    gpio_set_dir(PIN_RESET, GPIO_OUT);
    gpio_set_dir(PIN_BL, GPIO_OUT);

    gpio_put(PIN_CS, 1);

    gpio_put(PIN_RESET, 1);
    sleep_ms(50);
    gpio_put(PIN_RESET, 0);
    sleep_ms(50);
    gpio_put(PIN_RESET, 1);
    sleep_ms(150);

    lcd_init(st7789_init_seq);
    gpio_put(PIN_BL, 1);

    gpio_init(25);
    gpio_set_dir(25, GPIO_OUT);

    lcd_clear(0x0000); 

    static uint8_t image_buffer[IMAGE_SIZE_BYTES];

    while (1) {
        int c = getchar_timeout_us(10000);
        if (c != PICO_ERROR_TIMEOUT) {
            char userInput = (char)c;

            if (userInput == 's') {
                putchar('A'); 
                fflush(stdout);

                int counter = 0;
                uint32_t timeout_counter = 0;

                while (counter < IMAGE_SIZE_BYTES) {
                    int b = getchar_timeout_us(100000); //100ms timeout per chunk
                    if (b != PICO_ERROR_TIMEOUT) {
                        image_buffer[counter++] = (uint8_t)b;
                        timeout_counter = 0; //reset stall tracker
                    } else {
                        timeout_counter++;
                        if (timeout_counter > 30) break; //Abort if transfer stalls for 3 seconds
                    }
                }

                if (counter == IMAGE_SIZE_BYTES) {
                    lcd_set_window();
                    st7789_start_pixels();
                    
                    const uint16_t *img_ptr = (const uint16_t *)image_buffer;

                    for (int y = 0; y < SCREEN_HEIGHT; ++y) {
                        for (int x = 0; x < SCREEN_WIDTH; ++x) {
                            uint16_t colour = img_ptr[y * SCREEN_WIDTH + x];
                            
                            uint8_t pixel_bytes[2] = { 
                                (uint8_t)(colour & 0xff), 
                                (uint8_t)(colour >> 8)    
                            };
                            
                            spi_write_blocking(spi0, pixel_bytes, 2);
                        }
                    }
                    lcd_set_dc_cs(1, 1);
                }
            } else if (userInput == '1') {
                gpio_put(25, 1);
            } else if (userInput == '0') {
                gpio_put(25, 0);
            }
        }
    }
}