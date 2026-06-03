import subprocess
import webbrowser
import time
import os
import sys

if getattr(sys, 'frozen', False):
    base = os.path.dirname(sys.executable)
else:
    base = os.path.dirname(os.path.abspath(__file__))

server = os.path.join(base, 'OrganizadorFinanceiro.exe')
subprocess.Popen([server], creationflags=0x08000000, cwd=base)
time.sleep(2)
try:
    subprocess.Popen(['msedge', '--app=http://localhost:5050', '--new-window'])
except FileNotFoundError:
    webbrowser.open('http://localhost:5050')
