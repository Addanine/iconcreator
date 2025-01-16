import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from PIL import Image, ImageOps, ImageChops
import colorsys
import os
import plistlib  # For reading Info.plist on macOS

#
#  --- Recoloring Functions (same as before) ---
#

def hue_shift_saturation(
    image: Image.Image, 
    target_hex: str, 
    sat_multiplier=1.0, 
    val_multiplier=1.0
) -> Image.Image:
    """
    Approach 1:
    Directly force the hue to match `target_hex`.
    Multiply saturation and value (brightness) by factors
    for more/less pastel or brightness.
    """
    # Convert target_hex (#RRGGBB) -> (R,G,B) in [0..1]
    target_rgb = tuple(int(target_hex[i : i + 2], 16) / 255.0 for i in (1, 3, 5))
    target_h, _, _ = colorsys.rgb_to_hsv(*target_rgb)

    rgba_image = image.convert("RGBA")
    alpha = rgba_image.getchannel("A")

    # Convert to RGB for pixel-level manipulation
    rgb_image = rgba_image.convert("RGB")
    pixels = rgb_image.load()

    width, height = rgb_image.size
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            # Force hue to target, tweak saturation & value
            h = target_h
            s = min(s * sat_multiplier, 1.0)
            v = min(v * val_multiplier, 1.0)
            nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
            pixels[x, y] = (
                int(nr * 255),
                int(ng * 255),
                int(nb * 255),
            )

    output = rgb_image.convert("RGBA")
    output.putalpha(alpha)
    return output

def grayscale_colorize(
    image: Image.Image, 
    target_hex_white: str, 
    target_hex_black: str
) -> Image.Image:
    """
    Approach 2:
    Convert image to Grayscale, then colorize:
      black -> target_hex_black
      white -> target_hex_white
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")

    gray = ImageOps.grayscale(rgba)
    colored = ImageOps.colorize(gray, black=target_hex_black, white=target_hex_white)

    colored_rgba = colored.convert("RGBA")
    colored_rgba.putalpha(alpha)
    return colored_rgba

def overlay_blend(
    image: Image.Image, 
    overlay_hex: str, 
    blend_mode="screen"
) -> Image.Image:
    """
    Approach 3:
    Create a solid color overlay and blend with the original.
      'screen' = lighten
      'multiply' = darken
    """
    rgba = image.convert("RGBA")
    solid_layer = Image.new("RGBA", rgba.size, overlay_hex)

    if blend_mode == "screen":
        blended = ImageChops.screen(rgba, solid_layer)
    elif blend_mode == "multiply":
        blended = ImageChops.multiply(rgba, solid_layer)
    else:
        blended = ImageChops.screen(rgba, solid_layer)  # default
    return blended

def resize_and_center_512(image: Image.Image) -> Image.Image:
    """
    Resize the image so the largest dimension = 512,
    then center it on a 512x512 transparent canvas.
    """
    image = image.convert("RGBA")
    w, h = image.size

    # Determine scale
    if w > h:
        new_w = 512
        new_h = int(h * (512.0 / w))
    else:
        new_h = 512
        new_w = int(w * (512.0 / h))

    # Resize with high-quality filter
    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Create blank 512x512
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))

    # Compute top-left to center
    x = (512 - new_w) // 2
    y = (512 - new_h) // 2

    canvas.paste(resized, (x, y), resized)
    return canvas

#
#  --- NEW FEATURE: Recolor .app bundles automatically ---
#

def pull_app_icon(app_path: str) -> str:
    """
    Given a path to MyApp.app, attempt to find the .icns icon:
      1. Read Info.plist for CFBundleIconFile (e.g. 'MyAppIcon' or 'AppIcon.icns')
      2. If no extension, add '.icns'
      3. Construct Resources/<iconfile>.icns path
    Returns full path to the .icns file or None if not found.
    """
    info_plist_path = os.path.join(app_path, "Contents", "Info.plist")
    if not os.path.isfile(info_plist_path):
        return None

    with open(info_plist_path, "rb") as f:
        plist_data = plistlib.load(f)

    icon_file = plist_data.get("CFBundleIconFile")
    if not icon_file:
        # not found
        return None

    # Ensure it ends with .icns
    if not icon_file.lower().endswith(".icns"):
        icon_file += ".icns"

    possible_path = os.path.join(app_path, "Contents", "Resources", icon_file)
    if os.path.isfile(possible_path):
        return possible_path

    return None

def recolor_app_icons(
    app_paths: list[str],
    recolor_function, 
    output_dir: str,
    **kwargs
):
    """
    For each .app in app_paths:
      1. Find the .icns path
      2. Load it in Pillow
      3. Recolor using `recolor_function(img, **kwargs)`
      4. Resize/center to 512x512
      5. Save as .icns to output_dir with the same .app name + .icns
    """
    for app_path in app_paths:
        if not app_path.lower().endswith(".app"):
            print(f"Skipping non-app: {app_path}")
            continue

        icon_path = pull_app_icon(app_path)
        if not icon_path:
            print(f"No icon found for: {app_path}")
            continue

        # Load the icon
        try:
            img = Image.open(icon_path)
        except Exception as e:
            print(f"Could not open icon for {app_path}: {e}")
            continue

        # Apply the recolor function
        recolored = recolor_function(img, **kwargs)

        # Center to 512x512
        final_512 = resize_and_center_512(recolored)

        # Construct output path:
        # e.g. if app_path = "/Applications/Safari.app"
        # then just get the basename "Safari.app" => "Safari" => "Safari.icns"
        base_app_name = os.path.splitext(os.path.basename(app_path))[0]
        out_icns_name = base_app_name + ".icns"
        out_path = os.path.join(output_dir, out_icns_name)

        # Save as .icns with multiple sizes for best macOS compatibility
        icon_sizes = [
            (16, 16),
            (32, 32),
            (64, 64),
            (128, 128),
            (256, 256),
            (512, 512),
        ]
        try:
            final_512.save(out_path, format="ICNS", sizes=icon_sizes)
            print(f"[OK] Recolored icon for {base_app_name} -> {out_path}")
        except Exception as e:
            print(f"[Error] Could not save .icns for {base_app_name}: {e}")

#
#  --- Main Script Entry Point ---
#

def main():
    root = tk.Tk()
    root.withdraw()

    # Prompt user for recoloring approach
    approach_msg = (
        "Which recoloring approach would you like?\n"
        "1 = Hue Shift (with optional saturation/brightness tweaks)\n"
        "2 = Grayscale + Colorize (two pinks)\n"
        "3 = Overlay (Screen or Multiply)\n\n"
        "Alternatively, type 'app' to recolor multiple .app bundles.\n"
        "(Enter 1, 2, 3, or 'app')"
    )
    approach_choice = simpledialog.askstring("Choose Approach", approach_msg)
    if not approach_choice:
        print("No approach chosen. Exiting.")
        return

    # If user chooses 'app', we handle the new feature
    if approach_choice.lower() == "app":
        # 1) Ask which approach we want for the actual recoloring
        sub_approach_msg = (
            "For the .app icons, pick a recolor approach:\n"
            "1 = Hue Shift\n"
            "2 = Grayscale + Colorize\n"
            "3 = Overlay\n"
        )
        sub_choice = simpledialog.askstring("Choose Recolor Approach", sub_approach_msg)
        if sub_choice not in {"1", "2", "3"}:
            messagebox.showerror("Error", "Invalid sub-choice for recolor. Exiting.")
            return

        # 2) Ask user for the main hex color
        target_hex = simpledialog.askstring(
            "Enter Hex Color",
            "Please enter the primary hex code (e.g. #FFB6C1):"
        )
        if not target_hex:
            print("No hex code entered. Exiting.")
            return

        # 3) Let user pick multiple .app bundles
        app_paths = filedialog.askopenfilenames(
            title="Select .app Bundles",
        )
        if not app_paths:
            print("No .app selected. Exiting.")
            return

        # 4) Ask user for an output directory
        output_dir = filedialog.askdirectory(
            title="Select output directory for recolored icons"
        )
        if not output_dir:
            print("No output directory selected. Exiting.")
            return

        # 5) Based on sub_choice, define our recolor function and params
        if sub_choice == "1":
            # Hue shift
            sat_str = simpledialog.askstring(
                "Saturation Multiplier",
                "Default 1.0 = no change.\n"
                "Less than 1.0 => more pastel. More than 1.0 => more vibrant."
            )
            val_str = simpledialog.askstring(
                "Brightness (Value) Multiplier",
                "Default 1.0 = no change.\n"
                "Greater than 1.0 => brighter."
            )
            try:
                sat_mult = float(sat_str) if sat_str else 1.0
            except ValueError:
                sat_mult = 1.0
            try:
                val_mult = float(val_str) if val_str else 1.0
            except ValueError:
                val_mult = 1.0

            def recolor_func(img):
                return hue_shift_saturation(
                    img, target_hex, sat_multiplier=sat_mult, val_multiplier=val_mult
                )

        elif sub_choice == "2":
            # Grayscale+colorize needs a second "dark" color
            darker_hex = simpledialog.askstring(
                "Enter 'black' Color",
                "Optional: Enter a darker hex for shadows.\n"
                "If blank, we'll auto-generate ~20% darker."
            )
            if not darker_hex:
                r = int(target_hex[1:3], 16)
                g = int(target_hex[3:5], 16)
                b = int(target_hex[5:7], 16)
                r = int(max(r * 0.8, 0))
                g = int(max(g * 0.8, 0))
                b = int(max(b * 0.8, 0))
                darker_hex = f"#{r:02X}{g:02X}{b:02X}"

            def recolor_func(img):
                return grayscale_colorize(img, target_hex_white=target_hex, target_hex_black=darker_hex)

        else:
            # Overlay approach
            blend_mode = simpledialog.askstring(
                "Blend Mode",
                "Choose 'screen' or 'multiply'. Default is 'screen' if invalid."
            )
            if blend_mode not in {"screen", "multiply"}:
                blend_mode = "screen"

            def recolor_func(img):
                return overlay_blend(img, target_hex, blend_mode)

        # 6) Recolor the icons from each .app
        recolor_app_icons(app_paths, recolor_func, output_dir)

        print("Done with .app recoloring feature!")
        return

    #
    # Otherwise, the user typed 1, 2, or 3 => the original single-file approach
    #

    if approach_choice not in {"1", "2", "3"}:
        messagebox.showerror("Error", "Invalid approach selection.")
        return

    # Ask user for the main hex color
    target_hex = simpledialog.askstring(
        "Enter Hex Color",
        "Please enter the primary hex code (e.g. #FFB6C1):"
    )
    if not target_hex:
        print("No hex code entered. Exiting.")
        return

    # Let user pick one or more images
    image_paths = filedialog.askopenfilenames(
        title="Select Images",
        filetypes=[
            ("Image Files", ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.webp")),
            ("All Files", "*.*"),
        ]
    )
    if not image_paths:
        print("No image selected. Exiting.")
        return

    # Additional prompts depending on approach
    if approach_choice == "1":
        # Hue shift
        sat_str = simpledialog.askstring(
            "Saturation Multiplier",
            "Default 1.0 = no change.\n"
            "Less than 1.0 => more pastel. More than 1.0 => more vibrant."
        )
        val_str = simpledialog.askstring(
            "Brightness (Value) Multiplier",
            "Default 1.0 = no change.\n"
            "Greater than 1.0 => brighter."
        )
        try:
            sat_mult = float(sat_str) if sat_str else 1.0
        except ValueError:
            sat_mult = 1.0
        try:
            val_mult = float(val_str) if val_str else 1.0
        except ValueError:
            val_mult = 1.0

    elif approach_choice == "2":
        # Grayscale+Colorize
        darker_hex = simpledialog.askstring(
            "Enter 'black' Color",
            "Optional: Enter a darker hex for shadows.\n"
            "If blank, we'll auto-generate ~20% darker."
        )
        if not darker_hex:
            r = int(target_hex[1:3], 16)
            g = int(target_hex[3:5], 16)
            b = int(target_hex[5:7], 16)
            r = int(max(r * 0.8, 0))
            g = int(max(g * 0.8, 0))
            b = int(max(b * 0.8, 0))
            darker_hex = f"#{r:02X}{g:02X}{b:02X}"

    else:
        # Overlay
        blend_mode = simpledialog.askstring(
            "Blend Mode",
            "Choose 'screen' or 'multiply'. Default is 'screen' if invalid."
        )
        if blend_mode not in {"screen", "multiply"}:
            blend_mode = "screen"

    # Process each selected file
    for path in image_paths:
        basename, _ = os.path.splitext(path)
        out_path = basename + ".icns"  # Save as .icns

        print(f"Processing {path} -> {out_path}")

        # Open the original
        img = Image.open(path)

        # Recolor
        if approach_choice == "1":
            recolored = hue_shift_saturation(img, target_hex, sat_mult, val_mult)
        elif approach_choice == "2":
            recolored = grayscale_colorize(img, target_hex, darker_hex)
        else:
            recolored = overlay_blend(img, target_hex, blend_mode)

        final_512 = resize_and_center_512(recolored)

        # Save .icns with multiple sizes
        icon_sizes = [(16,16), (32,32), (64,64), (128,128), (256,256), (512,512)]
        final_512.save(
            out_path,
            format="ICNS",
            sizes=icon_sizes
        )
        print(f"Saved: {out_path}")

    print("Done with standard recoloring approach.")

if __name__ == "__main__":
    main()

