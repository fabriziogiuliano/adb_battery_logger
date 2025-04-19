./adb shell "pm list packages -d | while read package; do am force-stop \$package; done"
./adb shell "pm list packages -d | while read package; do pm disable \$package; done"
./adb shell "pm -D list packages -d | while read package; do pkill \$package; done"
