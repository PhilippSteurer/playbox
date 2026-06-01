# Raspberry Pi Zero 2W Pin Configuration

## Hardware Pin Assignments

### RC522 RFID Reader (SPI)
| Physical Pin | BCM GPIO | Function | Purpose |
|--------------|----------|----------|---------|
| 24           | GPIO8    | SPI CE0  | Chip Select |
| 23           | GPIO11   | SCKL     | Serial Clock |
| 19           | GPIO10   | MOSI     | Master Out, Slave In |
| 21           | GPIO9    | MISO     | Master In, Slave Out |
| 18           | GPIO24   | IRQ      | Interrupt Request |
| 22           | GPIO25   | RST      | Reset |

### WM8960 Audio HAT (I2C + I2S)
| Physical Pin | BCM GPIO | Function | Purpose |
|--------------|----------|----------|---------|
| 3            | GPIO2    | I2C1 SDA | I2C Serial Data (Codec Control) |
| 5            | GPIO3    | I2C1 SCL | I2C Serial Clock (Codec Control) |
| 12           | GPIO18   | I2S CLK  | I2S Bit Clock |
| 35           | GPIO19   | I2S FS   | I2S Frame Sync (LRCLK) |
| 38           | GPIO20   | I2S ADC  | I2S Audio Data In |
| 40           | GPIO21   | I2S DAC  | I2S Audio Data Out |

### Power & Ground
| Physical Pin | Signal | Used By |
|--------------|--------|---------|
| 1, 17        | 3.3V   | RFID (3.3V), Audio HAT |
| 6, 9, 20, 25 | GND    | All modules |

## Hardware Button Inputs (Freely Available)
Assign the following GPIO pins for playback control buttons:
- **GPIO27** (Physical Pin 13): Play/Pause
- **GPIO22** (Physical Pin 15): Volume Up
- **GPIO23** (Physical Pin 16): Volume Down
- **GPIO4** (Physical Pin 7): Previous Track (optional)
- **GPIO14** (Physical Pin 8): Next Track (optional)

*Note: Ensure adequate debounce timing (50-100ms) in button handlers to avoid multiple triggers.*

## I2C & SPI Configuration
- **I2C1**: GPIO2 (SDA), GPIO3 (SCL) - WM8960 codec communication
- **SPI0**: GPIO8-11 - RC522 RFID reader communication
- Both must be enabled via `raspi-config` or device tree overlays
