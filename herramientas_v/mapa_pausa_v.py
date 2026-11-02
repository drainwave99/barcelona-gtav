"""Plano de Barcelona en la pestaña MAPA del menú de pausa del juego.

El mapa del menú pinta dos capas: los dibujos de levels/gta5/minimap.rpf (Los Santos: quitar_ls lo saca) y,
debajo, una cuadrícula de texturas minimap_sea_<fila>_<columna> (fila 0 = norte) que dice
x64a.rpf/data/tune/minimap.ymt (2 x 3 de 4500 m, para Los Santos). Aquí:
  - la cuadrícula (2 x 3, como la del juego) se estira sobre la rejilla del radar (radar_v: 7 x 9 bloques de
    2048 m), con texturas de 2048 px (3,5 x 3 m/px): minimap_sea_<fila>_<columna>.ytd. El juego solo las busca en scaleform_generic.rpf (en un
    DLC no las encuentra y el menú se queda cargando): quitar_ls rehace ese RPF de update.rpf con las suyas
    cambiadas por estas (meter_en);
  - minimap.ymt con esa cuadrícula y el plano siempre dibujado; quitar_ls lo mete en update.rpf
    (x64/data/tune y x64/patch/data/tune, que mandan sobre x64a.rpf).
  - sin la niebla de guerra (fBaseAlpha 1): si no, en el rectángulo de Los Santos solo se ve lo ya recorrido.
Como es el mapa del propio juego, el marcador (clic derecho), los iconos y el GPS caen en su sitio.

python mapa_pausa_v.py   rehace las teselas con lo último de radar_v (mod_v/radar/xml) y el minimap.ymt
                         (luego quitar_ls.py, con el juego cerrado, para meterlos en el juego)
"""
import re
import sys

from PIL import Image

import config_v
import rage

RADAR = config_v.MOD / "radar"
OBRA = config_v.MOD / "mapa_pausa"
YMT = OBRA / "minimap.ymt"
TESELAS = OBRA / "teselas"            # los minimap_sea_*.ytd en binario


def _rejilla():
    import radar_v
    return radar_v.X0, radar_v.Y0, radar_v.BLOQUE, radar_v.NBX, radar_v.NBY, radar_v.MAR


# cuántas teselas: las del juego son 2 x 3 (con más, el menú se quedaba cargando); cada una cubre un trozo de la
# rejilla del radar
COLS, FILAS, PX_TESELA = 2, 3, 2048



def teselas(imagenes):
    """imagenes: {(bx, by): imagen PIL del bloque (norte arriba)}. Hace un ytd por casilla de la rejilla."""
    x0, y0, bloque, nbx, nby, mar = _rejilla()
    import shutil
    xml = OBRA / "teselas_xml"
    shutil.rmtree(xml, ignore_errors=True)
    shutil.rmtree(TESELAS, ignore_errors=True)
    xml.mkdir(parents=True)
    # el plano entero a 4 m/px (norte arriba), troceado en COLS x FILAS
    k = 512
    todo = Image.new("RGB", (nbx * k, nby * k), mar)
    for (bx, by), img in imagenes.items():
        todo.paste(img.convert("RGB").resize((k, k), Image.LANCZOS), (bx * k, (nby - 1 - by) * k))
    w, h = todo.width / COLS, todo.height / FILAS
    for f in range(FILAS):
        for c in range(COLS):
            trozo = todo.crop((round(c * w), round(f * h), round((c + 1) * w), round((f + 1) * h)))
            n = f"minimap_sea_{f}_{c}"
            rage.escribir_ytd(xml / f"{n}.ytd.xml", {n: (trozo.resize((PX_TESELA, PX_TESELA), Image.LANCZOS), False)})
    rage.a_binario(xml, TESELAS)


def meter_en(raiz, gta, copia):
    """Deja en raiz/x64/data/cdimages/scaleform_generic.rpf/ lo del de update.rpf (de la copia sin tocar) con
    nuestras teselas: cwtool meter cambia ese RPF entero por la carpeta."""
    import shutil
    destino = raiz / "x64" / "data" / "cdimages" / "scaleform_generic.rpf"
    r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "abrir", str(gta), str(copia), str(destino),
                             "solo:" + "\\".join([copia.name, "x64", "data", "cdimages", "scaleform_generic.rpf"])], capture_output=True, text=True)
    if r.returncode != 0 or not (destino / "minimap_sea_0_0.ytd").exists():
        raise RuntimeError("no se pudo sacar scaleform_generic.rpf: " + r.stdout[-300:] + r.stderr[-500:])
    for viejo in destino.glob("minimap_sea_*.ytd"):
        viejo.unlink()
    n = 0
    for t in TESELAS.glob("minimap_sea_*.ytd"):
        shutil.copy2(t, destino / t.name)
        n += 1
    print(f"scaleform_generic.rpf: {n} teselas del mapa del menú")


def imagenes_de_radar():
    """Recompone cada bloque (4 x 4 texturas t<i><j> de 256 px; j desde el sur) con los .dds que dejó radar_v."""
    x0, y0, bloque, nbx, nby, _ = _rejilla()
    out = {}
    for d in (RADAR / "xml").glob("bcnradar_*_*.ytd"):
        m = re.fullmatch(r"bcnradar_(\d+)_(\d+)\.ytd", d.name)
        if not m or not d.is_dir():
            continue
        bx, by = int(m.group(1)), int(m.group(2))
        img = Image.new("RGB", (1024, 1024))
        for i in range(4):
            for j in range(4):
                t = Image.open(d / f"t{i}{j}.dds").convert("RGB").resize((256, 256))
                img.paste(t, (i * 256, (3 - j) * 256))
        out[(bx, by)] = img
    return out


YMT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<CTuningFile>
 <Tunables>
  <Item type="CMiniMap__Tunables">
   <Name>hash_B3BBE4A1</Name>
   <Sonar>
    <fSoundRange_BarelyAudible value="1" />
    <fSoundRange_MostlyAudible value="1.8" />
    <fSoundRange_ClearlyAudible value="8" />
    <fSoundRange_Whisper value="10" />
    <fSoundRange_Talking value="15" />
    <fSoundRange_Shouting value="30" />
    <fSoundRange_Megaphone value="35" />
    <fSoundRange_FootstepBase value="20" />
    <fSoundRange_HeavyFootstep value="17.5" />
    <fSoundRange_FootstepFoliage value="10" />
    <fSoundRange_LandFromFall value="17.5" />
    <fSoundRange_WeaponSpinUp value="10" />
    <fSoundRange_Gunshot value="30" />
    <fSoundRange_SilencedGunshot value="10" />
    <fSoundRange_ProjectileLanding value="5" />
    <fSoundRange_Explosion value="50" />
    <fSoundRange_ObjectCollision value="10" />
    <fSoundRange_GlassBreak value="25" />
    <fSoundRange_CarHorn value="15" />
    <fSoundRange_CarLowSpeed value="10" />
    <fSoundRange_CarHighSpeed value="30" />
    <fSoundRange_WaterSplashSmall value="10" />
    <fSoundRange_WaterSplashLarge value="20" />
    <fMinListenerRangeToDrawSonarBlips value="50" />
    <fRainSnowSoundReductionAmount value="3" />
    <fRadioSoundReductionAmount value="3" />
    <fRadioSoundReductionDistance value="3" />
    <fConversationSoundReductionAmount value="3" />
    <fConversationSoundReductionDistance value="3" />
   </Sonar>
   <HealthBar>
    <fStaminaDepletionBlinkPercentage value="0.1" />
    <iHealthDepletionBlinkPercentage value="25" />
   </HealthBar>
   <Bitmap>
    <iBitmapTilesX value="{cols}" />
    <iBitmapTilesY value="{filas}" />
    <vBitmapTileSize x="{tx:.0f}" y="{ty:.0f}" />
    <vBitmapStart x="{x0:.0f}" y="{y1:.0f}" />
    <bAlwaysDrawBitmap value="true" />
    <eBitmapForPause>MM_BITMAP_VERSION_SEA</eBitmapForPause>
    <eBitmapForMinimap>MM_BITMAP_VERSION_MINIMAP</eBitmapForMinimap>
   </Bitmap>
   <!-- niebla de guerra: con fBaseAlpha 0, en este rectángulo (Los Santos) solo se veía lo ya visitado -->
   <FogOfWar>
    <fWorldX value="-3447" />
    <fWorldY value="-7722" />
    <fWorldW value="7647" />
    <fWorldH value="11368" />
    <fBaseAlpha value="1" />
    <fTopAlpha value="1" />
    <fFowWaterHeight value="50" />
   </FogOfWar>
   <Camera>
    <fPauseMenuTilt value="80" />
    <fBitmapRequiredZoom value="80" />
    <fExteriorFootZoom value="83" />
    <fExteriorFootZoomRunning value="90" />
    <fExteriorFootZoomWanted value="60" />
    <fExteriorFootZoomWantedRunning value="45" />
    <fExteriorFootTilt value="0" />
    <fExteriorFootOffset value="30" />
    <fInteriorFootZoom value="500" />
    <fInteriorFootTilt value="0" />
    <fInteriorFootOffset value="30" />
    <fParachutingZoom value="72" />
    <fVehicleStaticZoom value="96" />
    <fVehicleStaticWantedZoom value="66" />
    <fVehicleMovingZoom value="48" />
    <fVehicleMovingWantedZoom value="48" />
    <fVehicleSpeedZoomScalar value="0.8" />
    <fVehicleTilt value="60" />
    <fVehicleOffset value="30" />
    <fAltimeterTilt value="60" />
    <fAltimeterOffset value="15" />
    <fBigmapTilt value="0" />
    <fBigmapOffset value="0" />
    <fRangeZoomedScalarStandard value="2.1" />
    <fRangeZoomedScalarPlane value="4.2" />
   </Camera>
   <Tiles>
    <vMiniMapWorldSize x="9400" y="12492" />
    <vMiniMapWorldStart x="-4500" y="8000" />
    <bDrawVectorSeaPaused value="false" />
    <bDrawVectorSeaMinimap value="true" />
   </Tiles>
   <Overlay>
    <vPos x="0" y="0" />
    <vScale x="100" y="100" />
    <fDisplayZ value="33" />
   </Overlay>
   <Display>
    <ScriptOverlayTime value="225" />
    <WantedOverlayTime value="500" />
    <MaskNormalAlpha value="0.7" />
    <MaskFlashAlpha value="0.7" />
   </Display>
  </Item>
 </Tunables>
</CTuningFile>
"""


def ymt():
    """Escribe y devuelve mod_v/mapa_pausa/minimap.ymt (binario PSO) con la cuadrícula de Barcelona."""
    x0, y0, lado, nbx, nby, _ = _rejilla()
    xml = YMT.parent / "xml"
    xml.mkdir(parents=True, exist_ok=True)
    texto = YMT_XML
    for k, v in dict(cols=COLS, filas=FILAS, tx=nbx * lado / COLS, ty=nby * lado / FILAS, lado=lado, x0=x0, y0=y0, y1=y0 + nby * lado, ancho=nbx * lado,
                     alto=nby * lado).items():
        texto = re.sub(r"\{" + k + r"(:[^}]*)?\}", lambda m, v=v: format(v, (m.group(1) or ":")[1:]), texto)
    (xml / "minimap.ymt.pso.xml").write_text(texto, encoding="utf-8")
    rage.a_binario(xml, YMT.parent)
    return YMT


if __name__ == "__main__":
    imgs = imagenes_de_radar()
    print(len(imgs), "bloques del radar")
    teselas(imgs)
    print(ymt(), ymt().stat().st_size, "bytes")
