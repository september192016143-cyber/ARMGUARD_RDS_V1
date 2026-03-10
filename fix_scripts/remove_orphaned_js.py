import re

TEMPLATE = r'C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1\project\armguard\templates\transactions\transaction_form.html'
with open(TEMPLATE, 'r', encoding='utf-8') as f:
    tmpl = f.read()

before = len(tmpl)

# Remove the F1 FIX comments + orphaned JS IIFE + stray </script>
tmpl = re.sub(
    r'(?s)\{# F1 FIX:.*?#\}\n\{# URLs.*?#\}\n\(function\(\)\{.*?\}\)\(\);\n</script>\n',
    '',
    tmpl
)

after = len(tmpl)
print(f'Removed {before - after} chars from orphaned JS block')

script_open = tmpl.count('<script')
script_close = tmpl.count('</script>')
print(f'script open tags: {script_open}')
print(f'script close tags: {script_close}')

with open(TEMPLATE, 'w', encoding='utf-8', newline='\n') as f:
    f.write(tmpl)
print('Saved.')
