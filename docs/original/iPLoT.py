from __future__ import annotations
try:
   import os
   iPLoTHOMEFILE=os.path.abspath(__file__)
   iPLoTHOMEDIR=os.path.dirname(iPLoTHOMEFILE)
   filename=os.path.join(iPLoTHOMEDIR,'iPLoT.txt')
   if os.path.exists(filename):
      exec(open(filename,'r',encoding='utf-8').read(),globals())
   else:
      print(filename+' does not exist')
except ImportError:
   pass

##############################################
### To generate the application
### pip install py2app
### py2applet --make-setup iPLoT.py
### python3 setup.py iPLoT.py
##############################################

##############################################
### import subprocess
### import sys
### To install a package like 'requests' from inside a script
### subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
##############################################
