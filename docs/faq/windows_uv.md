# FAQ: How do I install **wildintel-tools** on Windows using **uv**?

Follow the steps below to correctly install **wildintel-tools** on a Windows system using **uv**.

---

## **1. Install Python**

1. Visit the official Python [Python website](https://www.python.org/downloads/windows/)
   ![Visit the official Python](faq_install_windows_uv_1.png)
3. Download the latest Windows installer. **Important:** Windows SmartScreen may block the download and show a warning. If this happens, **click “Keep”** to allow the download to continue.
   ![Visit the official Python](faq_install_windows_uv_2.png)
5. Run the installer and **enable the option “Add Python to PATH”** and press **Install now**.
   ![Visit the official Python](faq_install_windows_uv_3.png)
7. Complete the installation.
---

## **2. Open PowerShell**

Open a **new PowerShell** window (no admin privileges required).

> **Tip:** Navigate to the folder where you want to work (e.g., `Documents`), then **hold the Shift key, right-> click**, and choose **“Open PowerShell window here”**. This ensures you start in the correct folder.

---

## **3. Install the required tools using `winget`**

Use the following commands to install Git, ExifTool, and uv:

### **Install Git**
```powershell
winget install -e --id Git.Git
```
![Install Git](faq_install_windows_uv_5.png)

### Install ExifTool

```powershell
winget install -e --id OliverBetz.ExifTool
```
![Install ExifTool](faq_install_windows_uv_6.png)

### Install uv

``` powershell
winget install -e --id astral-sh.uv
```
![Install uv](faq_install_windows_uv_7.png)

## 4. Close the terminal

After installing the tools, close PowerShell completely. This ensures that PATH updates take effect.

## 5. Reopen PowerShell

Open a new PowerShell session.

## 6. Go to your Documents folder

``` powershell
cd $HOME\Documents
```

## 7. Clone the wildintel-tools repository

``` powershell
git clone https://github.com/ijfvianauhu/wildintel-tools.git
```
![Clone the wildintel-tools repository](faq_install_windows_uv_9.png)


## 8. Enter the repository

``` powershell
cd wildintel-tools
```
![Enter the repository](faq_install_windows_uv_10.png)


## 9. Checkout the correct version (v0.1.0)

``` powershell
git checkout v0.1.0
```
![Checkout the correct version](faq_install_windows_uv_11.png)

## 10. Run wildintel-tools using uv

``` powershell
uv run wildintel-tools
```
![Run wildintel-tools using uv](faq_install_windows_uv_12.png.png)

## 11. Configure connection with Trapper

1. View all available configuration options:

```
uv run wildintel-tools config show
```

2. Set the Trapper login (username):

```
uv run wildintel-tools config set GENERAL.login your_username
```

3. Set the Trapper password:

```
wildintel-tools config set GENERAL.password your_password
```

4. Test the connection to Trapper:

```
uv run wildintel-tools helpers test-connection
```

You should see a confirmation if the connection is successful.
