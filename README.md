# Secure Password Manager
 With this program you will be able to create random passwords with the length you desire. The passwords will be saved in the same directory your console is.
 You can also edit the password generating another one or even delete a file you don't need anymore.

<p align="center">
   <img src="https://github.com/santipvz/SecurePasswordManager/actions/workflows/pylint.yml/badge.svg/" alt="Tests">
   <img src="https://img.shields.io/badge/Version-1.0-blue/" alt="Static Badge">
   
</p>

 ## Usage
First of all, you can install this project with `pip install sec-pass-manager`

There are 2 ways for using this program.
### 1. Graphical interface
All you need to do type `spm` on your console.

After that a window will popup where you can create, delete or edit a file that contains username and password:
<p align="center">
  <img src="assets/create_graphical.png" width="250" style="margin: 10px;">
  <img src="assets/delete_graphical.png" width="250" style="margin: 10px;">
  <img src="assets/edit_graphical.png" width="250" style="margin: 10px;">
</p>

### 2. Console
This is a more direct way to manage the files using the console command `cpass`. Now you will see an example of each function:

<p align="center">
  <img src="assets/console_commands.png" width="780" style="margin: 10px;">
</p>
<pre><code>cpass create --filename test --username pingu --length 24</code></pre>
<pre><code>cpass edit --filename test --username pingu2 --length 12</code></pre>
<pre><code>cpass delete --filename test</code></pre>

There is also de reduced commands
<pre><code>cpass create -f test -u pingu -l 24</code></pre>
<pre><code>cpass edit -f test -u pingu2 -l 12</code></pre>
<pre><code>cpass delete -f test</code></pre>

> [!NOTE]
> This program will create `.key` files that you can open with any notepad as if it was a `.txt`<br><br>If you don't indicate a length it will be set to 10 as default.
