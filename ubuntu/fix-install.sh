#!/bin/bash
cd /usr/lib/python3/dist-packages
ls -la | grep "apt_pkg.cpython"
sudo cp apt_pkg.cpython-38-x86_64-linux-gnu.so apt_pkg.so
echo "Done Fixing .."