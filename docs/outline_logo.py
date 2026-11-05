"""Outline the supplied FrameIt wordmark with its exact Simpletix face.

This is a recipe for this artwork, not a general SVG text-layout engine.
FontTools is regeneration tooling only; readers/builds use the committed SVG.
"""

import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont


def outline_wordmark(font_path: Path, output: Path) -> None:
    folder = Path(__file__).parent / 'source/_static/logo'
    master = folder / 'frameit_logo_vector.svg'
    if output.resolve() in {master.resolve(), (folder / 'frameit_logo_symbol_vector.svg').resolve(), font_path.resolve()}:
        raise ValueError('Refusing to replace source artwork or the font')
    font = TTFont(font_path)
    if font['name'].getDebugName(4) != 'simpletix':
        raise ValueError('Exact Simpletix is required; no font substitution')
    tree = ET.parse(master)
    root = tree.getroot()
    svg = '{http://www.w3.org/2000/svg}'
    text = root.find(svg + 'text')
    if (text is None or ''.join(text.itertext()) != 'FrameIt'
            or text.find(".//" + svg + "tspan[@id='tspan4']").get('rotate') != '0 0 0'
            or 'text-anchor:middle' not in text.get('style', '')):
        raise ValueError('Source composition changed; review this specific export recipe')
    size = float(re.search(r'font-size:([0-9.]+)px', text.get('style')).group(1))
    scale = size / font['head'].unitsPerEm
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    advances = [font['hmtx'][cmap[ord(c)]][0] * scale for c in 'FrameIt']
    x, y = float(text.get('x')) - sum(advances)/2, float(text.get('y'))
    group = ET.Element(svg + 'g', {'id': 'outlined-wordmark', 'aria-label': 'FrameIt'})
    for index, (character, advance) in enumerate(zip('FrameIt', advances, strict=True)):
        pen = SVGPathPen(glyphs)
        glyphs[cmap[ord(character)]].draw(pen)
        fill = '#00978F' if index == 0 else '#EC7600' if index >= 5 else '#021633'
        ET.SubElement(group, svg + 'path', {
            'd': pen.getCommands(), 'fill': fill,
            'transform': f'translate({x:.8f} {y}) scale({scale:.10f} {-scale:.10f})',
        })
        x += advance
    root.insert(list(root).index(text), group)
    root.remove(text)
    ET.register_namespace('', svg[1:-1])
    ET.indent(tree, space='  ')
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding='utf-8', xml_declaration=True)
    print(f"Outlined with {font['name'].getDebugName(4)}, {font['name'].getDebugName(5)}: {output}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    outline_wordmark(args.font, args.output)
