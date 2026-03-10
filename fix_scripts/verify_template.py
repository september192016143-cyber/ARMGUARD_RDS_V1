import re

content = open(
    r'C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1\project\armguard\templates\transactions\transaction_form.html',
    encoding='utf-8'
).read()

lines = content.splitlines()
print('=== First 15 lines ===')
for i, l in enumerate(lines[:15], 1):
    print(f'{i:3}: {l}')

print()
blocks_extra_js = re.findall(r'\{% block extra_js %\}', content)
print(f'block extra_js count: {len(blocks_extra_js)}')
print(f'script open tags: {content.count("<script")}')
print(f'script close tags: {content.count("</script>")}')
print(f'onclick= count: {content.count("onclick=")}')
print(f'onchange= count: {content.count("onchange=")}')
print(f'onfocus= count: {content.count("onfocus=")}')
print(f'onblur= count: {content.count("onblur=")}')
