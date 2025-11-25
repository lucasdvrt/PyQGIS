# DGAC - Mission Impact PEB Aérodrome français 
# Code de génération automatique de carte d'impact sur QGIS
# Testé sur QGIS 3.40 et 3.44

from PyQt5 import *
from PyQt5.QtCore import *

import xml.etree.ElementTree
import time
import shutil
import os
import re
import tempfile
import uuid
import requests
import json

from urllib.parse import quote
from datetime import datetime
from qgis.PyQt.QtGui import QImage, QPainter, QColor
from qgis.core import QgsLegendStyle
from pathlib import Path


# Définir le chemin principal
myPath = Path.home() / 'Downloads'

date = datetime.today()
aujourdhui_en = date.strftime("%Y%m%d")
aujourdhui_fr = date.strftime("%d/%m/%Y")

myBoldFont=QtGui.QFont('Verdana', 11)
myBoldFont.setBold(True)

myTitleBoldFont=QtGui.QFont('Verdana', 24)
myTitleBoldFont.setBold(True)

myMetaFont=QtGui.QFont('Verdana', 8)
myMetaFont.setItalic(True)


# URL Logo Internet de la DGAC
url = r'https://o-flair.fr/wp-content/uploads/2020/11/1200px-DGAC.svg_.png'
response = requests.get(url)

image_originale1 = myPath / 'dgac.png'
path_nouvelle_image1 = myPath / 'dgac2.png'

# Téléchargement du logo
if response.status_code == 200:
    with open(image_originale1, 'wb') as file:
        file.write(response.content)
else:
    raise Exception('Impossible de télécharger la photo !')

# Ajouter un fond derrière le logo
my_image = QImage(str(image_originale1))
largeur = my_image.width() + 40
hauteur = my_image.height() + 40

nouvelle_image1 = QImage(largeur, hauteur, QImage.Format_ARGB32)
nouvelle_image1.fill(QColor(255, 255, 255))

painter = QPainter(nouvelle_image1)

x_offset = (largeur - my_image.width()) // 2
y_offset = (hauteur - my_image.height()) // 2

painter.drawImage(x_offset, y_offset, my_image) 
painter.end()

nouvelle_image1.save(str(path_nouvelle_image1))


# Préparer le projet et la génération de couche
project = QgsProject.instance()
iface.mapCanvas().refresh()
manager = project.layoutManager()

# Supprimer les couches existantes
project.removeAllMapLayers()
project.clear()

time.sleep(1)
iface.mapCanvas().refresh()

# Définir le CRS du projet
crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
project.setCrs(crs)
project.setEllipsoid('EPSG:4326')

time.sleep(1)
iface.mapCanvas().refresh()

# Définir le chemin des dossiers Cartes et Données
_cartes = myPath / '_cartes'
if os.path.isdir(_cartes) == True:
    shutil.rmtree(_cartes)
if os.path.isdir(_cartes) == False:
    os.mkdir(_cartes)
_donnees = myPath / '_donnees'
if os.path.isdir(_donnees) == False:
    os.mkdir(_donnees)


time.sleep(1)

# Fond OSM
urlWithParams = "type=xyz&url=http://tile.openstreetmap.org/{z}/{x}/{y}.png"
osm = QgsRasterLayer(urlWithParams, "OpenStreetMap", "wms")

# Couche WFS IGN
# Définir les composants de l'URL
base_url = "https://data.geopf.fr/wfs/ows"
type_name = "BDTOPO_V3:aerodrome"

# Définir le filtre CQL
cql_filter_str = "nature='Aérodrome'"

# Encoder le filtre pour l'URL 
encoded_filter = quote(cql_filter_str) 

# Construire l'URI complet avec le filtre
params = (
    "service=WFS"
    "&version=2.0.0"
    "&request=GetFeature"
    f"&typeName={type_name}"
    f"&cql_filter={encoded_filter}" 
)
wfs_uri = base_url + "?" + params

mes_aerodromes_wfs = QgsVectorLayer(wfs_uri, "Aérodromes", "WFS")

# Définir un chemin pour le fichier GeoPackage temporaire
local_gpkg_path = str(_donnees / 'aerodromes_filtres.gpkg')

# Enregistrer la couche WFS dans ce fichier
QgsVectorFileWriter.writeAsVectorFormat(
    mes_aerodromes_wfs,
    local_gpkg_path,
    'utf-8',
    mes_aerodromes_wfs.crs(),
    'GPKG' 
)

# Supprimer la couche WFS (on n'en a plus besoin)
project.removeMapLayer(mes_aerodromes_wfs)

# Charger le fichier GeoPackage local pour le reste du script
mes_aerodromes = QgsVectorLayer(local_gpkg_path, "Aérodromes", "ogr")
if not mes_aerodromes.isValid():
    raise Exception("ERREUR: Le fichier GeoPackage local n'a pas pu être chargé.")

print(f"Couche locale 'Aérodromes' chargée : {mes_aerodromes.featureCount()}")

# Ouvrir les couches
project.addMapLayer(osm)
osm.setOpacity(0.75)
project.addMapLayer(mes_aerodromes)

# Modifier le nom d'affichage
mes_aerodromes = project.mapLayersByName("Aérodromes")[0]


# Copier la couche des aérodromes
aerodrome_unique = mes_aerodromes.clone()
aerodrome_unique.setName('Pour sélection')
project.addMapLayer(aerodrome_unique)

# Organiser l'ordre des couches
root = project.layerTreeRoot()
root.setHasCustomLayerOrder (True)
order = root.customLayerOrder()
order.insert(0, order.pop(order.index(aerodrome_unique)))
order.insert(1, order.pop(order.index(mes_aerodromes)))
order.insert(3, order.pop(order.index(osm)))
root.setCustomLayerOrder( order )

# Zoom sur les aérodromes
extent_mes_aerodromes = mes_aerodromes.extent()
iface.mapCanvas().setExtent(extent_mes_aerodromes)
iface.mapCanvas().refresh()
time.sleep(0.5)

# Démarrage de la boucle de génération
jeuDeTest = list(mes_aerodromes.getFeatures())
for feat in jeuDeTest[-5:]:  # for feat in mes_sommets.getFeatures(): pour l'entièreté des données

    # Réinitialiser les couches
    peb_layer = None
    bati_final_layer = None
    plu_final_layer = None
    
    # Définir les champs clés pour la boucle
    id_aerodrome = feat['cleabs']
    aerodrome_name = feat['toponyme']
    code_oaci = feat['code_icao'] 

    # Gérer les noms vides (NULL) ou les chaînes vides
    if not aerodrome_name: 
        aerodrome_name = f"Aerodrome_ID_{id_aerodrome}"
    else:
        aerodrome_name = str(aerodrome_name)

    # Nettoyer le nom pour le système de fichiers
    safe_name = re.sub(r'[^\w\s-]', '', aerodrome_name)
    
    # Remplacer les espaces par des underscores
    safe_name = safe_name.strip().replace(' ', '_')
    
    # S'assurer que le nom n'est pas vide après nettoyage
    if not safe_name:
        safe_name = f"Aerodrome_ID_{id_aerodrome}"
        
    peb_name = "Impact_PEB"

    # Créer le nom de mise en page (layout) final et unique
    layoutName = f"{peb_name}_{safe_name}"

    print('\n' + layoutName.replace("'", '') + ' : OK !')

    # Filtrage et Symbologie des Aérodromes 
    expr_filtre = u"cleabs = '{}'".format(id_aerodrome)
    aerodrome_unique.setSubsetString(expr_filtre)
    aerodrome_unique.setName(layoutName)
    
    symbol_aerodrome_unique = QgsFillSymbol.createSimple({'style': 'solid','color': '1,66,128,150', 'outline_style': 'no'})
    aerodrome_unique.renderer().setSymbol(symbol_aerodrome_unique)
    aerodrome_unique.triggerRepaint()

    expr_exclusion = u"cleabs <> '{}'".format(id_aerodrome)
    mes_aerodromes.setSubsetString(expr_exclusion)
    mes_aerodromes.setName('Autres aérodromes')
    
    symbol_mes_aerodromes = QgsFillSymbol.createSimple({'style': 'solid','color': '100,100,100,100','outline_color': 'grey','outline_width': 0.25})
    mes_aerodromes.renderer().setSymbol(symbol_mes_aerodromes)
    mes_aerodromes.triggerRepaint()

    iface.layerTreeView().refreshLayerSymbology(aerodrome_unique.id())
    iface.layerTreeView().refreshLayerSymbology(mes_aerodromes.id())
    iface.mapCanvas().refresh()

    # Préparation du Layout 
    layouts_list = manager.printLayouts()
    for l in layouts_list:
        if l.name() == layoutName:
            manager.removeLayout(l)
            
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(layoutName)
    manager.addLayout(layout)

    # Chargement du WFS du PEB 
    # On filtre le WFS en utilisant le champ 'code OACI'
    peb_uri = (
        "service=WFS&version=2.0.0&request=GetFeature"
        "&typeName=dgac_peb_plan_wfs:dgac_peb_plan_wfs"
        f"&cql_filter=code_oaci='{code_oaci}'" 
    )
    url_wfs = "https://data.geopf.fr/wfs/ows?" + peb_uri
    peb_layer = QgsVectorLayer(url_wfs, f"PEB {code_oaci}", "WFS")

    # DÉFINITION DU FLAG et VARIABLES STATS (PLACEHOLDERS)
    if peb_layer.isValid() and peb_layer.featureCount() > 0:
        a_un_peb = True
        project.addMapLayer(peb_layer)

        print(f"Sauvegarde locale de {layoutName}...")
        
        # Définir un chemin local (base du nom choisie : PEB + code OACI + date)
        date_str = datetime.now().strftime("%Y%m%d")
        base_name = f"peb_{code_oaci}_{date_str}"
        local_peb_path = _donnees / f"{base_name}.gpkg"

        # Ajouter un compteur si le fichier existe déjà (identer les couches)
        counter = 1
        while os.path.exists(local_peb_path):
            local_peb_path = _donnees / f"{base_name}_{counter}.gpkg"
            counter += 1
       
        # Sauvegarder la couche
        QgsVectorFileWriter.writeAsVectorFormat(
            peb_layer,
            str(local_peb_path),
            'utf-8',
            peb_layer.crs(), 
            'GPKG'
        )
        print(f"PEB sauvegardé dans : {local_peb_path}")

        # Charger ce fichier local
        peb_local_layer = QgsVectorLayer(str(local_peb_path), f"PEB {code_oaci}", "ogr")
        
        if not peb_local_layer.isValid():
            print("ERREUR: Impossible de charger le PEB local, on saute les géotraitements.")
            a_un_peb = False 
        else:
            # On supprime l'ancienne couche WFS (on n'en a plus besoin)
            project.removeMapLayer(peb_layer)
            
            # On DÉFINIT la couche locale comme couche 'peb_layer'
            peb_layer = peb_local_layer

    # Définir les catégories
        categories = [
            ('A', '#FF0000', 'ZONE A: \nzone de bruit très fort'),
            ('B', '#FFA500', 'ZONE B: \nzone de bruit fort'),
            ('C', '#00B050', 'ZONE C: \nzone de bruit modéré'),
            ('D', '#0000FF', 'ZONE D: \nzone de bruit faible')
        ]

        # Créer la liste d'objets QgsRendererCategory
        renderer_categories = []
        for value, color, label in categories:
            # Créer le symbole
            symbol = QgsFillSymbol.createSimple({
                'color': color,
                'outline_style': 'no',  
            })
            
            # Créer la catégorie (valeur, symbole, étiquette)
            cat = QgsRendererCategory(value, symbol, label)
            renderer_categories.append(cat)
            
        # Créer le moteur de rendu directement avec le champ 'zone'
        renderer = QgsCategorizedSymbolRenderer('zone', renderer_categories)
        
        # Appliquer le renderer avant d'ajouter la couche
        peb_layer.setRenderer(renderer)
        
        # Ajouter la couche au projet
        project.addMapLayer(peb_layer) 
        
        peb_layer.setOpacity(0.35) # (0.7 = 70% opaque)
        
        root = project.layerTreeRoot()
        
        if not root.hasCustomLayerOrder():
            root.setHasCustomLayerOrder(True)
        
        # Récupérer l'ordre actuel 
        order = root.customLayerOrder()
        
        # Essayer de retirer l'objet peb_layer
        try:
            order.pop(order.index(peb_layer))
        except ValueError:
            pass
        
        # Insérer l'OBJET peb_layer au début 
        order.insert(0, peb_layer)
        
        # Appliquer le nouvel ordre
        root.setCustomLayerOrder(order)
        
        # Rafraîchir les panneaux
        peb_layer.triggerRepaint()
        iface.layerTreeView().refreshLayerSymbology(peb_layer.id())

        # Début des traitements pour le PEB
        print(f"Début des géotraitements pour {layoutName}...")
        
        # Calculer l'emprise BBOX du PEB (en EPSG:4326) pour filtrer les WFS
        peb_extent_wgs84 = QgsRectangle()
        peb_extent_wgs84.setMinimal()
        
        # On projette l'emprise du PEB en WGS84 (EPSG:4326) pour le filtre BBOX
        source_crs = peb_layer.crs()
        dest_crs = QgsCoordinateReferenceSystem('EPSG:4326')
        xform = QgsCoordinateTransform(source_crs, dest_crs, project)
        
        # On itère sur les entités PEB pour obtenir l'emprise totale
        for f in peb_layer.getFeatures():
            geom_wgs84 = f.geometry()
            geom_wgs84.transform(xform) # On transforme la géométrie
            peb_extent_wgs84.combineExtentWith(geom_wgs84.boundingBox())
            
        # Formater l'emprise pour l'URL WFS (minX,minY,maxX,maxY)
        peb_bbox_str = (
            f"{peb_extent_wgs84.xMinimum()},{peb_extent_wgs84.yMinimum()},"
            f"{peb_extent_wgs84.xMaximum()},{peb_extent_wgs84.yMaximum()}"
        )
        
        # Initialiser les variables de statistiques
        stats_bati_zone_a = 0
        stats_bati_zone_b = 0
        stats_bati_zone_c = 0
        stats_bati_zone_d = 0
        stats_plu_surface_m2 = 0.0
        date_arret_peb = ""

        # Ouverture de la couche Bâti - BDTOPO
        bati_type_name = "BDTOPO_V3:batiment" 

        print("Chargement WFS Bâti et PLU...")
        bati_uri = f"service=WFS&version=2.0.0&request=GetFeature&typeName={bati_type_name}&bbox={peb_bbox_str},EPSG:4326"
        bati_layer = QgsVectorLayer("https://data.geopf.fr/wfs/ows?" + bati_uri, "Bâti (temp)", "WFS")
        
        # Traitement Bâti 
        if not bati_layer.isValid() or bati_layer.featureCount() == 0:
            print("Avertissement: Couche 'Bâti' non valide ou vide.")
        else:
            print(f"Couche 'Bâti' (WFS) chargée: {bati_layer.featureCount()} entités.")
            
            # Création de la couche d'affichage
            # On découpe le bâti total par le PEB total
            print("Découpage du Bâti par le PEB (pour affichage)...")
            result_bati_clipped = processing.run("native:clip", {
                'INPUT': bati_layer,
                'OVERLAY': peb_layer, # Utilise le PEB corrigé
                'OUTPUT': 'memory:'
            })
            
            bati_final_layer = result_bati_clipped['OUTPUT']
            
            if bati_final_layer.featureCount() > 0:
                bati_final_layer.setName("Bâti impacté")
                
                # Sauvegarde locale du Bâti impacté 
                print(f"Export du bâti impacté pour {code_oaci}...")
                
                # Définir le chemin de sortie
                out_bati_path = str(_donnees / f"bati_impacte_{code_oaci}.gpkg")
                
                # Supprimer l'ancien fichier s'il existe (pour éviter les conflits)
                if os.path.exists(out_bati_path):
                    try:
                        os.remove(out_bati_path)
                    except Exception as e:
                        print(f"Avertissement: Impossible de supprimer l'ancien fichier: {e}")

                # Sauvegarder la couche
                QgsVectorFileWriter.writeAsVectorFormat(
                    bati_final_layer,
                    out_bati_path,
                    'utf-8',
                    bati_final_layer.crs(),
                    'GPKG'
                )
                print(f"Bâti impacté sauvegardé dans : {out_bati_path}")
                
                # Symbologie du bâti 
                bati_symbol = QgsFillSymbol.createSimple({'color': '#000000', 'outline_style': 'no', 'opacity': '0.8'})
                bati_final_layer.setRenderer(QgsSingleSymbolRenderer(bati_symbol))
                
                project.addMapLayer(bati_final_layer, False)
                
                # Forcer l'ordre (sous le PEB)
                root = project.layerTreeRoot()
                node_bati = root.addLayer(bati_final_layer)
                order = root.customLayerOrder()
                order.insert(1, bati_final_layer) # 0=PEB, 1=Bâti
                root.setCustomLayerOrder(order)
            else:
                print("Aucun bâti ne superpose le PEB (pour l'affichage).")
                

            # Boucle des statistiques
            for zone_letter in ['A', 'B', 'C', 'D']:
                print(f"Traitement Bâti Zone {zone_letter}...")
                
                result_peb_zone = processing.run("native:extractbyexpression", {
                    'INPUT': peb_layer, 
                    'EXPRESSION': f"\"zone\" = '{zone_letter}'",
                    'OUTPUT': 'memory:'
                })
                
                result_intersection = processing.run("native:extractbylocation", {
                    'INPUT': bati_layer, 
                    'PREDICATE': [0], 
                    'INTERSECT': result_peb_zone['OUTPUT'],
                    'OUTPUT': 'memory:'
                })
                                
                # Compter les bâtiments dans le résultat
                count = result_intersection['OUTPUT'].featureCount()
                print(f"Résultat Zone {zone_letter}: {count} bâtiments.")
                
                if zone_letter == 'A': stats_bati_zone_a = count
                elif zone_letter == 'B': stats_bati_zone_b = count
                elif zone_letter == 'C': stats_bati_zone_c = count
                elif zone_letter == 'D': stats_bati_zone_d = count


        # Traitement du PLU 
        # Filtre "Zones constructibles" : tout ce qui commence par U ou AU
        filtre_plu_constructible = '("typezone" LIKE \'U%\' OR "typezone" LIKE \'AU%\')'

        print("\nPréparation du PEB pour extraction PLU via Apicarto...")

        # Dissoudre PEB
        result_peb_dissolved = processing.run("native:dissolve", {
            'INPUT': peb_layer,
            'OUTPUT': 'memory:'
        })
        peb_dissolved_layer = result_peb_dissolved['OUTPUT']

        # Reprojeter en WGS84
        result_peb_wgs84 = processing.run("native:reprojectlayer", {
            'INPUT': peb_dissolved_layer,
            'TARGET_CRS': 'EPSG:4326',
            'OUTPUT': 'memory:'
        })
        peb_wgs84_layer = result_peb_wgs84['OUTPUT']

        # Géométrie GeoJSON
        try:
            peb_geom = next(peb_wgs84_layer.getFeatures()).geometry()
            geom_geojson = json.loads(peb_geom.asJson())
        except:
            print("ERREUR: PEB géométrie GeoJSON introuvable.")
            geom_geojson = None

        if geom_geojson:

            print("Appel API CARTO → zones urbaines (PLU)...")
            api_url = "https://apicarto.ign.fr/api/gpu/zone-urba"
            payload = {"geom": geom_geojson, "epsg": 4326}

            try:
                response = requests.post(api_url, json=payload)
                response.raise_for_status()

                # Sauvegarde stable temporaire 
                tmp_geojson_path = os.path.join(
                    tempfile.gettempdir(),
                    f"plu_api_{code_oaci}_{uuid.uuid4()}.geojson"
                )

                with open(tmp_geojson_path, "w", encoding="utf-8") as f:
                    f.write(response.text)

                # Charger le GeoJSON dans QGIS
                plu_layer = QgsVectorLayer(tmp_geojson_path,
                                           f"PLU_API_{code_oaci}", "ogr")

                if not plu_layer.isValid():
                    print("ERREUR: PLU API Carto chargé mais invalide.")
                    stats_plu_surface_m2 = 0.0

                else:
                    print(f"PLU chargé : {plu_layer.featureCount()} entités")

                    # Extraction zones constructibles U / AU
                    result_constructible = processing.run("native:extractbyexpression", {
                        'INPUT': plu_layer,
                        'EXPRESSION': filtre_plu_constructible,
                        'OUTPUT': 'memory:'
                    })
                    constructible_layer = result_constructible['OUTPUT']
                    nb_constructible = constructible_layer.featureCount()

                    print(f"Zones constructibles trouvées : {nb_constructible}")

                    if nb_constructible > 0:

                        # Intersection PLU constructible / PEB                 
                        # Définir le chemin de sortie
                        date_str = datetime.now().strftime("%Y%m%d")
                        base_name_plu = f"plu_constructible_{code_oaci}_{date_str}"
                        local_plu_path = _donnees / f"{base_name_plu}.gpkg"

                        # Ajouter un compteur si le fichier existe déjà
                        counter = 1
                        while os.path.exists(local_plu_path):
                            local_plu_path = _donnees / f"{base_name_plu}_{counter}.gpkg"
                            counter += 1
         
                        # Géotraitement intersection 
                        processing.run("native:intersection", {
                            'INPUT': constructible_layer,
                            'OVERLAY': peb_layer,
                            'OUTPUT': str(local_plu_path)
                        })

                        print(f"PLU constructible intersecté sauvegardé → {local_plu_path.name}")

                        intersected_layer = str(local_plu_path)

                        if os.path.exists(intersected_layer):

                            # Reprojection en L93
                            reprojected = processing.run("native:reprojectlayer", {
                                'INPUT': intersected_layer,
                                'TARGET_CRS': 'EPSG:2154',
                                'OUTPUT': 'memory:'
                            })['OUTPUT']

                            # Calcul de la surface
                            area_layer = processing.run("native:fieldcalculator", {
                                'INPUT': reprojected,
                                'FIELD_NAME': 'calc_area',
                                'FIELD_TYPE': 0,
                                'FIELD_LENGTH': 12,
                                'FIELD_PRECISION': 2,
                                'FORMULA': '$area',
                                'OUTPUT': 'memory:'
                            })['OUTPUT']

                            stats_plu_surface_m2 = sum(
                                f['calc_area'] for f in area_layer.getFeatures()
                            )

                            print(f"Surface constructible intersectée : "
                                  f"{stats_plu_surface_m2:,.2f} m²")
                                  
                            # On charge la couche depuis le fichier gpkg pour l'afficher
                            plu_final_layer = QgsVectorLayer(str(local_plu_path), "PLU Constructible", "ogr")
                            
                            if plu_final_layer.isValid():
                                # Appliquer une symbologie 
                                plu_symbol = QgsFillSymbol.createSimple({
                                    'color': '255,127,0,100', 
                                    'style': 'b_diagonal',    
                                    'outline_color': '255,127,0',
                                    'outline_width': '0.1'
                                })
                                plu_final_layer.setRenderer(QgsSingleSymbolRenderer(plu_symbol))
                                
                                # Ajouter au projet
                                project.addMapLayer(plu_final_layer, False)
                                root = project.layerTreeRoot()
                                node_plu = root.addLayer(plu_final_layer)
                                
                                # Forcer l'ordre (On veut : 0=Bâti, 1=PLU, 2=PEB...)
                                order = root.customLayerOrder()
                                order.insert(1, plu_final_layer) 
                                root.setCustomLayerOrder(order)

                        else:
                            print("Aucune zone constructible n'intersecte le PEB.")
                            stats_plu_surface_m2 = 0.0

                    else:
                        print("Aucune zone constructible U / AU trouvée.")
                        stats_plu_surface_m2 = 0.0

                # Nettoyage fichier temporaire 
                try:
                    os.remove(tmp_geojson_path)
                except:
                    pass

            except Exception as e:
                print(f"ERREUR API Carto : {e}")
                stats_plu_surface_m2 = 0.0
        
        
        # Récupération de la date d'arrêt
        try:
            peb_feature = next(peb_layer.getFeatures())
            date_arret_peb = peb_feature['date_arret'] 
        except Exception:
            date_arret_peb = "Non spécifiée"
            
    else:
        a_un_peb = False

    # Ajout de la carte (MAP)
    map = QgsLayoutItemMap(layout)
    map.setRect(20, 20, 20, 20)
    
    aero_geom = feat.geometry()
    aero_extent = aero_geom.boundingBox()
    
    # On crée l'emprise finale en copiant celle de l'aérodrome
    final_extent = QgsRectangle(aero_extent)
    
    if a_un_peb:
        # CAS 1: ON A UN PEB
        try:
            # On boucle sur les entités du PEB pour trouver leur emprise totale
            for peb_feat in peb_layer.getFeatures():
                final_extent.combineExtentWith(peb_feat.geometry().boundingBox())
            
            # On applique l'emprise combinée (Aéro + PEB)
            map.setExtent(final_extent)
            
            # On ajoute une petite marge de 20% pour ne rien couper
            map.setScale(map.scale() * 1.2) 
            
        except Exception as e:
            print(f"Erreur calcul emprise PEB: {e}. On se rabat sur l'aérodrome.")
            map.setExtent(aero_extent)
            map.setScale(map.scale() * 3.0) # Marge de 300%
            
    else:
        # CAS 2: PAS DE PEB
        # On applique l'emprise de l'aérodrome seul
        map.setExtent(aero_extent)
        
        # On ajoute une GRANDE marge de 300% pour voir le contexte
        map.setScale(75000)
    
    
    layout.addLayoutItem(map)
    map.attemptMove(QgsLayoutPoint(5, 27, QgsUnitTypes.LayoutMillimeters))
    map.attemptResize(QgsLayoutSize(220, 178, QgsUnitTypes.LayoutMillimeters))
    map.setFrameEnabled(True)

    # AJOUT DU TITRE ET SOUS-TITRE
    title = QgsLayoutItemLabel(layout)
    title.setText(aerodrome_name) # Utilise le nom de l'aérodrome
    title.setFont(myTitleBoldFont) # Police du script original
    title.adjustSizeToText()
    layout.addLayoutItem(title)
    title.attemptMove(QgsLayoutPoint(5, 4, QgsUnitTypes.LayoutMillimeters))
    title.attemptResize(QgsLayoutSize(220, 20, QgsUnitTypes.LayoutMillimeters))
     
    subtitle = QgsLayoutItemLabel(layout)
    subtitle.setText(f"Code OACI : {code_oaci}") # Sous-titre
    subtitle.setFont(QFont('Verdana', 17)) # Police du script original
    subtitle.setFontColor(QColor(6, 77, 114))
    subtitle.adjustSizeToText()
    layout.addLayoutItem(subtitle)
    subtitle.attemptMove(QgsLayoutPoint(5, 17, QgsUnitTypes.LayoutMillimeters))
    subtitle.attemptResize(QgsLayoutSize(220, 20, QgsUnitTypes.LayoutMillimeters))

    # AJOUT DE LA LÉGENDE
    legend = QgsLayoutItemLegend(layout)
    legend_x = 230
    legend_y = 30 
    legend_largeur = 65
    legend_hauteur = 80
    legend.setTitle('Légende')
    
    legendTitleFont = QtGui.QFont('Verdana', 16)
    legendTitleFont.setBold(True)
    
    legend.setStyleFont(QgsLegendStyle.Title, legendTitleFont)
    legend.setStyleFont(QgsLegendStyle.Group, legendTitleFont)
    
    layout.addLayoutItem(legend)
    
    legend.attemptMove(QgsLayoutPoint(legend_x, legend_y, QgsUnitTypes.LayoutMillimeters))
    legend.attemptResize(QgsLayoutSize(legend_largeur, legend_hauteur, QgsUnitTypes.LayoutMillimeters))


    # On garde la construction manuelle du modèle 
    legend.setAutoUpdateModel(False) 
    model = legend.model()
    root_group = model.rootGroup()
    
    root_group.removeAllChildren()
    
    node_aero_unique = root_group.addLayer(aerodrome_unique)
    node_aero_unique.setName("Emprise de l'aérodrome")
 
    root_group.addLayer(mes_aerodromes)

    if 'plu_final_layer' in locals() and plu_final_layer and plu_final_layer.isValid():
        node_plu = root_group.addLayer(plu_final_layer)
        node_plu.setName("Zones constructibles (PLU)")
    
    if 'bati_final_layer' in locals() and bati_final_layer and bati_final_layer.isValid():
        node_plu = root_group.addLayer(bati_final_layer)
        node_plu.setName("Bâti impacté")  
    
    if a_un_peb and peb_layer.isValid():
        root_group.addLayer(peb_layer)    

    legend.adjustBoxSize()

    # AJOUT DU BLOC DE TEXTE STATISTIQUES 
    
    x_pos = 230
    y_pos = 135
    largeur = 60 # Largeur en mm
    
    titre_stats = QgsLayoutItemLabel(layout)
    titre_stats.setText("Analyse d'impact PEB")
    titre_stats.setFont(myBoldFont) # 'Verdana', 11, Bold
    layout.addLayoutItem(titre_stats)
    titre_stats.attemptMove(QgsLayoutPoint(x_pos, y_pos, QgsUnitTypes.LayoutMillimeters))
    titre_stats.attemptResize(QgsLayoutSize(largeur, 10, QgsUnitTypes.LayoutMillimeters))

    if a_un_peb:
        # On a un PEB : on formate les statistiques
        
        # On formate la surface : entier (int), séparateur espace
        surf_str = f"{int(stats_plu_surface_m2):,}".replace(',', ' ')
        
        texte_contenu = (
            f"Bâti en zone A : {stats_bati_zone_a}\n"
            f"Bâti en zone B : {stats_bati_zone_b}\n"
            f"Bâti en zone C : {stats_bati_zone_c}\n"
            f"Bâti en zone D : {stats_bati_zone_d}\n"
            f"\nSurface constructible (PLU) :\n"
            f"{surf_str} m²" # Formate le nombre (ex: 12 345 m²)
        )

        # Ajout de la date d'arrêt
        if date_arret_peb:
        # On vérifie si c'est bien un objet QDate
            if isinstance(date_arret_peb, QDate):
                # On le convertit en string au format "jour/mois/année"
                date_str = date_arret_peb.toString("dd/MM/yyyy")
            else:
                date_str = str(date_arret_peb) # Sécurité

            label_date = QgsLayoutItemLabel(layout)
            # On utilise la nouvelle variable 'date_str'
            label_date.setText(f"PEB approuvé le : {date_str}")
            label_date.setFont(myMetaFont) # 'Verdana', 8, Italic
            label_date.setHAlign(Qt.AlignLeft)
            layout.addLayoutItem(label_date)
            # On le place en bas à droite
            label_date.attemptMove(QgsLayoutPoint(x_pos, 190, QgsUnitTypes.LayoutMillimeters)) 
            label_date.attemptResize(QgsLayoutSize(largeur, 10, QgsUnitTypes.LayoutMillimeters))
        
    else:
        # Pas de PEB : on affiche le message de secours
        texte_contenu = "Pas de PEB existant pour cet aérodrome."

    contenu_stats = QgsLayoutItemLabel(layout)
    contenu_stats.setText(texte_contenu)
    contenu_stats.setFont(QFont('Verdana', 11))
    contenu_stats.setVAlign(Qt.AlignTop) # Aligner le texte en haut
    layout.addLayoutItem(contenu_stats)
    # On le place juste sous le titre
    contenu_stats.attemptMove(QgsLayoutPoint(x_pos, y_pos + 8, QgsUnitTypes.LayoutMillimeters))
    contenu_stats.attemptResize(QgsLayoutSize(largeur, 100, QgsUnitTypes.LayoutMillimeters))

    # AJOUT DES AUTRES ÉLÉMENTS (Métadonnées, Échelle, Logos...)
    
    # Meta 
    meta2 = QgsLayoutItemLabel(layout)
    meta2.setText(f"Carte générée le {aujourdhui_fr} avec QGIS {Qgis.QGIS_VERSION}")
    meta2.setFont(myMetaFont)
    layout.addLayoutItem(meta2)
    meta2.attemptMove(QgsLayoutPoint(20, 200, QgsUnitTypes.LayoutMillimeters))
    meta2.attemptResize(QgsLayoutSize(204, 8, QgsUnitTypes.LayoutMillimeters))
    meta2.setHAlign(Qt.AlignRight)
    
    # --- FLÈCHE DU NORD ---
    fleche_nord = QgsLayoutItemPicture(layout)
    
    # Utilise la flèche par défaut des ressources internes de QGIS
    fleche_nord.setPicturePath(":/images/north_arrows/layout_default_north_arrow.svg")
    
    layout.addLayoutItem(fleche_nord)
    
    # Redimensionner (15mm x 15mm est une bonne taille standard)
    fleche_nord.attemptResize(QgsLayoutSize(15, 15, QgsUnitTypes.LayoutMillimeters))
    
    # Positionner (Coin haut-gauche de la carte)
    # La carte commence à x=5, y=27. On la décale un peu pour qu'elle soit "dans" la carte.
    fleche_nord.attemptMove(QgsLayoutPoint(8, 30, QgsUnitTypes.LayoutMillimeters))


    # BARRE D'ÉCHELLE ADAPTATIVE
    scalebar = QgsLayoutItemScaleBar(layout)
    scalebar.setStyle('Single Box')
    scalebar.setUnits(QgsUnitTypes.DistanceMeters)
    scalebar.setLinkedMap(map)
    scalebar.setUnitLabel('mètres')
    scalebar.setFont(QFont('Verdana', 10))
    
    # On force 2 segments à droite pour un look standard
    scalebar.setNumberOfSegments(2)
    scalebar.setNumberOfSegmentsLeft(0)

    # CALCUL AUTOMATIQUE DE L'UNITÉ 
    # Récupérer l'échelle de la carte actuelle
    echelle_actuelle = map.scale() 
    
    # Calculer la distance terrain pour avoir un segment d'environ 2.5 cm (0.025m) sur papier
    distance_ideale = 0.025 * echelle_actuelle
    
    # Fonction pour arrondir à un chiffre "rond" (100, 250, 500, 1000...)
    import math
    def trouver_arrondi(valeur):
        if valeur <= 0: return 100
        # Trouver l'ordre de grandeur (10, 100, 1000...)
        puissance = 10 ** math.floor(math.log10(valeur))
        base = valeur / puissance
        
        # Choisir le multiple le plus proche (1, 2, 5, 10)
        if base < 1.5: multiple = 1
        elif base < 3.5: multiple = 2.5 # (250m est souvent plus joli que 200m)
        elif base < 7.5: multiple = 5
        else: multiple = 10
        
        return int(multiple * puissance)

    # Appliquer l'unité calculée
    unite_segment = trouver_arrondi(distance_ideale)
    scalebar.setUnitsPerSegment(unite_segment)
    
    scalebar.update()
    layout.addLayoutItem(scalebar)
    scalebar.attemptMove(QgsLayoutPoint(10, 188, QgsUnitTypes.LayoutMillimeters))

    # Ajouter le logo de la DGAC 
    my_logo1 = QgsLayoutItemPicture(layout)
    my_logo1.setPicturePath(str(path_nouvelle_image1))
    layout.addLayoutItem(my_logo1)
    my_logo1.attemptResize(QgsLayoutSize(21, 22, QgsUnitTypes.LayoutMillimeters))
    my_logo1.attemptMove(QgsLayoutPoint(273,3, QgsUnitTypes.LayoutMillimeters))

    # EXPORT PDF 
    file_name = f"{aujourdhui_en}-{layoutName}.pdf"
    export_path = myPath / "_cartes" / file_name
    
    exporter = QgsLayoutExporter(layout) # Utiliser le 'layout' de cette boucle
    
    map.refresh()
    
    exporter.exportToPdf(str(export_path), QgsLayoutExporter.PdfExportSettings())
    
    # On retire le layout de la mémoire
    manager.removeLayout(layout)

# FIN DE LA BOUCLE
