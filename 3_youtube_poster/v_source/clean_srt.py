#!/usr/bin/env python3
import re
import sys

srt_file = 'subtitles_ko.srt'
if len(sys.argv) > 1:
    srt_file = sys.argv[1]

with open(srt_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Remove markdown and explanatory text
content = re.sub(r'^.*?```(?:srt)?\s*\n?', '', content, flags=re.DOTALL)
content = re.sub(r'\n?\s*```.*?$', '', content, flags=re.DOTALL)

# Find first subtitle number
lines = content.split('\n')
start_idx = 0
for i, line in enumerate(lines):
    if line.strip().isdigit():
        start_idx = i
        break

content = '\n'.join(lines[start_idx:]).strip()

with open(srt_file, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'✅ Cleaned SRT file: {srt_file}')
print(f'First 15 lines:')
print('\n'.join(content.split('\n')[:15]))

