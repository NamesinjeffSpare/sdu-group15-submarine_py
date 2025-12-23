import time
from RGB import RGB

rgb = RGB()

while True:
    print("RED")
    rgb.set(0)
    time.sleep(1)
    rgb.off()
    print("GREEN")
    rgb.set(1)
    time.sleep(1)
    rgb.off()
    print("BLUE")
    rgb.set(2)
    time.sleep(1)
    rgb.off()
    print("OFF")
    rgb.off()
    time.sleep(1)
    break
