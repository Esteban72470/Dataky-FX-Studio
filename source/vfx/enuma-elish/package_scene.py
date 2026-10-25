"""Package the editable handwritten recipe and an isolated native Studio scene."""
from pathlib import Path
import argparse
import json
import shutil
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=HERE/'exports'/'package',help='Package output directory')
OUTPUT=parser.parse_args().output.resolve()
if OUTPUT==HERE or OUTPUT==HERE/'exports' or OUTPUT==HERE/'textures':
    parser.error('Choose a package directory separate from the sources and generated exports.')
OUTPUT.mkdir(parents=True,exist_ok=True)


def item(parent,cls,name):
    node=ET.SubElement(parent,'Item',{'class':cls})
    props=ET.SubElement(node,'Properties')
    ET.SubElement(props,'string',{'name':'Name'}).text=name
    return node,props


def prop(props,kind,name,value):
    node=ET.SubElement(props,kind,{'name':name})
    if isinstance(value,(tuple,list)):
        for axis,v in zip('RGB'if kind=='Color3'else'XYZ',value):ET.SubElement(node,axis).text=str(v)
    else:node.text=str(value)
    return node


root=ET.Element('roblox',{'version':'4'})
ET.SubElement(root,'External').text='null';ET.SubElement(root,'External').text='nil'
world,_=item(root,'Workspace','Workspace')
ground,gp=item(world,'Part','EnumaPreviewGround')
prop(gp,'bool','Anchored','true');prop(gp,'Vector3','size',[200,1,200]);prop(gp,'Color3','Color',[.035,.025,.04])
cf=ET.SubElement(gp,'CoordinateFrame',{'name':'CFrame'})
for key,value in zip(['X','Y','Z','R00','R01','R02','R10','R11','R12','R20','R21','R22'],[0,-.5,0,1,0,0,0,1,0,0,0,1]):ET.SubElement(cf,key).text=str(value)
_,lp=item(root,'Lighting','Lighting')
prop(lp,'float','ClockTime',0);prop(lp,'float','Brightness',1)
prop(lp,'Color3','Ambient',[.035,.025,.055]);prop(lp,'Color3','OutdoorAmbient',[.035,.025,.055])
light=root.find("./Item[@class='Lighting']")
_,bp=item(light,'BloomEffect','EnumaBloom');prop(bp,'float','Intensity',.8);prop(bp,'float','Size',40);prop(bp,'float','Threshold',1.6)
rs,_=item(root,'ReplicatedStorage','ReplicatedStorage')
_,mp=item(rs,'ModuleScript','EnumaElish')
prop(mp,'ProtectedString','Source',(HERE/'exports/Enuma-Elish.lua').read_text(encoding='utf-8'))
starter,_=item(root,'StarterPlayer','StarterPlayer')
scripts,_=item(starter,'StarterPlayerScripts','StarterPlayerScripts')
_,sp=item(scripts,'LocalScript','EnumaPreview')
controller=(HERE/'native_preview.lua').read_text(encoding='utf-8')
prop(sp,'ProtectedString','Source',controller)
scene=OUTPUT/'Scene-Enuma-Elish.rbxlx'
ET.ElementTree(root).write(scene,encoding='utf-8',xml_declaration=True)
for file in (HERE/'exports').iterdir():
    if file.is_file():shutil.copy2(file,OUTPUT/file.name)
for name in ('build_effect.py','draw_textures.py','textures.json','manifest.json','native_preview.lua'):
    shutil.copy2(HERE/name,OUTPUT/name)
shutil.copytree(HERE/'textures',OUTPUT/'textures',dirs_exist_ok=True)
install=r'''$ErrorActionPreference='Stop'
$textureSource=Join-Path $PSScriptRoot 'textures'
$versionsRoot=Join-Path $env:LOCALAPPDATA 'Roblox\Versions'
$versions=Get-ChildItem -LiteralPath $versionsRoot -Directory | Where-Object {Test-Path -LiteralPath (Join-Path $_.FullName 'RobloxStudioBeta.exe')}
if(-not $versions){throw 'Roblox Studio introuvable. Installer Studio puis relancer ce script.'}
foreach($version in $versions){
    $textureTarget=Join-Path $version.FullName 'content\textures\dataky-local\enuma-elish'
    New-Item -ItemType Directory -Path $textureTarget -Force | Out-Null
    Get-ChildItem -LiteralPath $textureSource -Filter '*.png' -File | Copy-Item -Destination $textureTarget
}
Write-Host 'Textures originales copiees pour la previsualisation locale dans Studio. Aucune publication effectuee.'
'''
(OUTPUT/'Installer-textures-Studio.ps1').write_text(install,encoding='utf-8-sig')
print(json.dumps({'scene':str(scene),'bytes':scene.stat().st_size,'textures':len(list((OUTPUT/'textures').glob('*.png')))}))
