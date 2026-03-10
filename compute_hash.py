import hashlib, base64
s = b"if(localStorage.getItem('sidebarCollapsed')==='true')document.body.classList.add('sidebar-collapsed');"
print("sha256-" + base64.b64encode(hashlib.sha256(s).digest()).decode())
