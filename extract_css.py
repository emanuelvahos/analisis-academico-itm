import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

style_match = re.search(r'<style>(.*?)</style>', content, flags=re.DOTALL)
if style_match:
    with open('static/style.css', 'w', encoding='utf-8') as f:
        f.write(style_match.group(1).strip())
    new_content = content.replace(style_match.group(0), '<link rel="stylesheet" href="/static/style.css">')
    new_content = new_content.replace('<script src="main.js"></script>', '<script src="/static/main.js"></script>')
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('CSS extracted and HTML updated')
else:
    print('No style tag found')
