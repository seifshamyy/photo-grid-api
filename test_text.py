import arabic_reshaper
from bidi.algorithm import get_display

text = 'الكوموا'

reshaped_text = arabic_reshaper.reshape(text)
bidi_text = get_display(reshaped_text)

print("Original chars:", [hex(ord(c)) for c in text])
print("Reshaped chars:", [hex(ord(c)) for c in reshaped_text])
print("Bidi chars:    ", [hex(ord(c)) for c in bidi_text])

invisible_chars = ['\u200e', '\u200f', '\u202a', '\u202b', '\u202c', '\u202d', '\u202e']
for char in invisible_chars:
    bidi_text = bidi_text.replace(char, '')

print("Cleaned Bidi:  ", [hex(ord(c)) for c in bidi_text])
