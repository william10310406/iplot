{code} 作業

這個資料夾裡有：
  {file}  作業本身，要改的是這個檔
  coursework.py  讓作業跑起來的程式，不用改
  {code}Space  作業用的資料（可能是空的）
  README.txt  這份說明

下面每一步要打的指令，都是單獨一行、前面空四格；整行複製、貼到終端機、按 Enter。

== macOS ==

第 1 步：裝 Python（只要做一次）
到 https://www.python.org/downloads/ 下載 macOS 的安裝程式（Python 3.10 以上），雙擊照著裝好。
已經裝過 python.org 的 Python 3.10 以上就跳過這一步。

第 2 步：打開「終端機」，進到這個資料夾
用 Spotlight（按 ⌘ 加空白鍵）找「終端機」打開。打 cd 再打一個空格（先不要按 Enter），
把這個 {code} 資料夾從 Finder 拖進終端機的視窗，再按 Enter。
之後每次重新打開終端機，都要先做這一步。

第 3 步：建 .venv（只要做一次）
作業用到的套件會裝在這個資料夾裡的 .venv，不會裝進電腦本身的 Python。

    {make_venv}

第 4 步：跑作業

    {run}

第一次跑會先裝作業用到的套件，要等幾分鐘。接著會列出可以跑的 case：打號碼、按 Enter，就會開視窗。
關掉一個視窗才會出現下一個。

改作業：用文字編輯器打開 {file}，改上半部，存檔，再做一次第 4 步。

== Windows（未經實機驗證）==

第 1 步：到 https://www.python.org/downloads/ 下載 Windows 的安裝程式（Python 3.10 以上），照著裝好。
第 2 步：在檔案總管打開這個 {code} 資料夾，在上面的網址列打 cmd、按 Enter，會開一個已經在這個資料夾裡的命令提示字元。
第 3 步：建 .venv（只要做一次）

    {win_make_venv}

第 4 步：跑作業

    {win_run}

== 交作業 ==

只交 {file}。coursework.py、{code}Space、.venv 都不用交。
