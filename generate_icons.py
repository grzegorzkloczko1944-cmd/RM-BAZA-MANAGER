#!/usr/bin/env python3
"""
Generuje ikony dla RM_MANAGER i RM_BAZA
- RM_MANAGER: biała litera "M" na czerwonym tle
- RM_BAZA: biała litera "B" na czerwonym tle
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(letter, output_path, size=256):
    """Tworzy ikonę z literą na czerwonym tle.
    
    Args:
        letter: Litera do wyświetlenia (M lub B)
        output_path: Ścieżka do pliku wyjściowego (.ico)
        size: Rozmiar ikony w pikselach
    """
    # Czerwone tło
    bg_color = (220, 53, 69)  # #dc3545 - Bootstrap danger red
    text_color = (255, 255, 255)  # Biały
    
    # Utwórz obraz
    img = Image.new('RGBA', (size, size), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Próbuj załadować font systemowy (fallback do domyślnego)
    # 0.9 = litery powiększone o 50% względem oryginalnych 0.6
    font_size = int(size * 0.9)
    try:
        # Windows
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        try:
            # Linux
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            # Fallback - domyślny font PIL
            font = ImageFont.load_default()
    
    # Wyśrodkuj tekst
    bbox = draw.textbbox((0, 0), letter, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (size - text_width) // 2 - bbox[0]
    y = (size - text_height) // 2 - bbox[1]
    
    # Rysuj tekst
    draw.text((x, y), letter, fill=text_color, font=font)
    
    # Zapisz jako .ico (Windows icon) z wieloma rozmiarami
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(output_path, format='ICO', sizes=icon_sizes)
    print(f"✅ Utworzono: {output_path}")
    
    # Zapisz również jako PNG (dla Tkinter)
    png_path = output_path.replace('.ico', '.png')
    img.save(png_path, format='PNG')
    print(f"✅ Utworzono: {png_path}")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Generuj ikony
    print("🎨 Generowanie ikon...")
    create_icon('M', os.path.join(script_dir, 'rm_manager_icon.ico'))
    create_icon('B', os.path.join(script_dir, 'rm_baza_icon.ico'))
    print("\n✅ Ikony wygenerowane pomyślnie!")
    print("\n📋 Kolejne kroki:")
    print("1. Ikony zostały zapisane w katalogu głównym projektu")
    print("2. Podczas kompilacji PyInstaller użyje ich automatycznie")
    print("3. W GUI ikony będą ustawione w oknie głównym")

if __name__ == '__main__':
    main()
