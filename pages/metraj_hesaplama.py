import streamlit as st

st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar
import pandas as pd
import comtypes.client
from collections import Counter
import numpy as np
import plotly.graph_objects as go

from database import save_hesaplama, get_hesaplamalar
from utils import top_right_login
from session_config import init_session_state

# Session state'i başlatıyoruz
init_session_state()

setup_sidebar()

# Üyelik sistemini sağ üstte gösteriyoruz
top_right_login()

# Title
st.title("ETABS Metraj ve 3D Model Görselleştirme")

# Initialize ETABS connection
with st.spinner("ETABS'e bağlanılıyor..."):
    comtypes.CoInitialize()
    try:
        etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        SapModel = etabs_object.SapModel
        st.success("ETABS'e başarıyla bağlanıldı!")
    except Exception as e:
        st.error(f"ETABS'e bağlanılırken hata oluştu: {e}")
        st.stop()

    # Set units to ton-meter
    SapModel.SetPresentUnits(12)

# Function to fetch table data from ETABS
def get_etabs_table(table_key, group_name="All"):
    field_key_list = []
    table_version = 1
    fields_keys_included = []
    number_records = 0
    table_data = []
    
    ret = SapModel.DatabaseTables.GetTableForDisplayArray(
        table_key, field_key_list, group_name, table_version,
        fields_keys_included, number_records, table_data
    )
    
    columns = ret[2]
    data_list = ret[4]
    num_columns = len(columns)
    rows = [data_list[i:i+num_columns] for i in range(0, len(data_list), num_columns)]
    
    return pd.DataFrame(rows, columns=columns)

# Fetch data for metraj calculation
with st.spinner("ETABS'ten metraj verileri alınıyor..."):
    df_modal = get_etabs_table('Material List by Story')
    df_beam = get_etabs_table('Beam Object Connectivity')
    df_wall = get_etabs_table('Wall Object Connectivity')
    df_frame = get_etabs_table('Frame Section Property Definitions - Concrete Rectangular')
    df_section = get_etabs_table('Material List by Section Property')
    df_wall_prop = get_etabs_table('Wall Property Definitions - Specified')
    df_story = get_etabs_table('Story Definitions')
    df_slab = get_etabs_table('Slab Property Definitions')

# Fetch data for 3D model
with st.spinner("ETABS'ten 3D model verileri alınıyor..."):
    df_point = get_etabs_table('Point Object Connectivity')
    df_column = get_etabs_table('Column Object Connectivity')
    df_floor = get_etabs_table('Floor Object Connectivity')
    df_area_sections = get_etabs_table('Area Assignments - Section Properties')
    df_slab_props = get_etabs_table('Slab Property Definitions')
    df_frame_sections = get_etabs_table('Frame Assignments - Section Properties')
    df_frame_props = get_etabs_table('Frame Section Property Definitions - Concrete Rectangular')

# Metraj Hesaplama
materials = df_modal["Material"].unique()
material_weights = {}

# Malzeme birim hacim ağırlıklarını al
for mat in materials:
    if mat not in ["None", "All"]:
        WeightPerVolume = SapModel.PropMaterial.GetWeightAndMass(mat)[0]
        material_weights[mat] = WeightPerVolume

df_modal["SelfWeight"] = df_modal["Material"].map(material_weights)
df_modal["Weight"] = pd.to_numeric(df_modal["Weight"], errors='coerce')
df_modal["Beton"] = df_modal["Weight"] / df_modal["SelfWeight"]

# Beam ve Wall ortak noktalar hesaplama
beam_points_list = df_beam["UniquePtI"].tolist() + df_beam["UniquePtJ"].tolist()
wall_points_list = df_wall["UniquePt3"].tolist() + df_wall["UniquePt4"].tolist()

beam_counter = Counter(beam_points_list)
wall_counter = Counter(wall_points_list)
common_points = set(beam_counter) & set(wall_counter)
common_count_beam = sum(beam_counter[pt] for pt in common_points)

# Tabloları birleştirme: Name ve Section sütunlarına göre t3 ve t2 sütunlarını ekleme
df_frame_subset = df_frame[['Name', 't3', 't2']]
df_merged = pd.merge(df_section, df_frame_subset, how='left', left_on='Section', right_on='Name')
df_merged = df_merged.drop(columns=['Name'])
df_merged = df_merged.rename(columns={'T3': 't3', 'T2': 't2'})

# Wall Property Definitions - Specified tablosundan Thickness sütununu ekleme
df_wall_prop_subset = df_wall_prop[['Name', 'Thickness']]
df_merged = pd.merge(df_merged, df_wall_prop_subset, how='left', left_on='Section', right_on='Name')
df_merged = df_merged.drop(columns=['Name'])

# Beam elemanları için ortalama t2 ve t3 hesaplama (ağırlıklı ortalama)
df_beams = df_merged[df_merged['ObjectType'] == 'Beam'].copy()
df_beams['t2'] = pd.to_numeric(df_beams['t2'], errors='coerce').fillna(0)
df_beams['t3'] = pd.to_numeric(df_beams['t3'], errors='coerce').fillna(0)
df_beams['NumPieces'] = pd.to_numeric(df_beams['NumPieces'], errors='coerce').fillna(0)

df_beams['NumPieces_t2'] = df_beams['NumPieces'] * df_beams['t2']
df_beams['NumPieces_t3'] = df_beams['NumPieces'] * df_beams['t3']

total_num_pieces = df_beams['NumPieces'].sum()
total_num_pieces_t2 = df_beams['NumPieces_t2'].sum()
total_num_pieces_t3 = df_beams['NumPieces_t3'].sum()

average_t2 = total_num_pieces_t2 / total_num_pieces if total_num_pieces > 0 else 0
average_t3 = total_num_pieces_t3 / total_num_pieces if total_num_pieces > 0 else 0

# Wall elemanları için ortalama Thickness hesaplama
df_walls = df_merged[df_merged['ObjectType'] == 'Wall'].copy()
df_walls['Thickness'] = pd.to_numeric(df_walls['Thickness'], errors='coerce').fillna(0)
df_walls['Weight'] = pd.to_numeric(df_walls['Weight'], errors='coerce').fillna(0)
df_walls['Thickness_Weight'] = df_walls['Thickness'] * df_walls['Weight']

total_weight = df_walls['Weight'].sum()
total_thickness_weight = df_walls['Thickness_Weight'].sum()

average_thickness = total_thickness_weight / total_weight if total_weight > 0 else 0

# Malzeme Bazlı SelfWeight Tablosunda güncelleme yapma
df_new = df_modal[['Story', 'ObjectType', 'Beton']].copy()

# "Sum" yazan satırları iptal et (filtrele)
df_new = df_new[df_new['Story'] != 'Sum']

# Sadece Beam elemanlarını filtrele
beam_mask = df_new['ObjectType'] == 'Beam'
df_beam_only = df_new[beam_mask].copy()

# Beton değerlerini sayısal hale getir
df_beam_only['Beton'] = pd.to_numeric(df_beam_only['Beton'], errors='coerce').fillna(0)

# Toplam Beton değerini hesapla
total_beton = df_beam_only['Beton'].sum()

# beton_eksi değerini hesapla
df_new["beton_eksi"] = common_count_beam * average_t2 * average_t3 * (average_thickness / 2)

# Her katın Beton değerinin toplam Beton'a oranını hesapla
df_beam_only['Beton_Ratio'] = df_beam_only['Beton'] / total_beton

# beton_eksi değerini oranlara göre dağıt
df_beam_only['Beton_Eksi_Pay'] = df_beam_only['Beton_Ratio'] * df_new["beton_eksi"].iloc[0]

# Yeni Beton değerini hesapla (orijinal Beton - pay)
df_beam_only['Beton_Guncel'] = df_beam_only['Beton'] - df_beam_only['Beton_Eksi_Pay']

# Güncellenmiş tabloyu oluştur
df_new.loc[beam_mask, 'Beton_Guncel'] = df_beam_only['Beton_Guncel']

# Orijinal tabloya güncellenmiş Beton sütununu ekle
df_new['Beton'] = pd.to_numeric(df_new['Beton'], errors='coerce').fillna(0)
df_new['Beton_Guncel'] = df_new['Beton_Guncel'].fillna(df_new['Beton'])  # Beam olmayanlar için orijinal Beton'u koru

# Beam elemanlarının toplam Length değerini hesapla
df_beams_section = df_section[df_section['ObjectType'] == 'Beam'].copy()
df_beams_section['Length'] = pd.to_numeric(df_beams_section['Length'], errors='coerce').fillna(0)
total_beam_length = df_beams_section['Length'].sum()

# Story Definitions Tablosu
df_story['Height'] = pd.to_numeric(df_story['Height'], errors='coerce').fillna(0)
average_story_height = df_story['Height'].mean()

# Slab Property Definitions Tablosu
df_slab_prop_subset = df_slab[['Name', 'Thickness']]
df_floors = df_section[df_section['ObjectType'] == 'Floor'].copy()
df_floors_merged = pd.merge(df_floors, df_slab_prop_subset, how='left', left_on='Section', right_on='Name')
df_floors_merged = df_floors_merged.drop(columns=['Name'])

df_floors_merged['Thickness'] = pd.to_numeric(df_floors_merged['Thickness'], errors='coerce').fillna(0)
df_floors_merged['Weight'] = pd.to_numeric(df_floors_merged['Weight'], errors='coerce').fillna(0)
df_floors_merged['Thickness_Weight'] = df_floors_merged['Thickness'] * df_floors_merged['Weight']
total_weight_floors = df_floors_merged['Weight'].sum()
total_thickness_weight = df_floors_merged['Thickness_Weight'].sum()

average_floor_thickness = total_thickness_weight / total_weight_floors if total_weight_floors > 0 else 0

# Perde_eksi_alan hesaplama
df_new['Perde_eksi_alan'] = 0.0
wall_mask = df_new['ObjectType'] == 'Wall'
df_new.loc[wall_mask, 'Perde_eksi_alan'] = (
    (df_new.loc[wall_mask, 'Beton'] / (average_thickness * average_story_height)) * average_floor_thickness
)

# Kiriş_eksi_alan hesaplama
total_kiris_eksi_alan = total_beam_length * average_floor_thickness * average_t2
beam_mask = df_new['ObjectType'] == 'Beam'
df_beam_only = df_new[beam_mask].copy()
df_beam_only['Beton'] = pd.to_numeric(df_beam_only['Beton'], errors='coerce').fillna(0)
total_beam_beton = df_beam_only['Beton'].sum()
df_beam_only['Beton_Ratio'] = df_beam_only['Beton'] / total_beam_beton
df_beam_only['Kiriş_eksi_alan'] = df_beam_only['Beton_Ratio'] * total_kiris_eksi_alan
df_new['Kiriş_eksi_alan'] = 0.0
df_new.loc[beam_mask, 'Kiriş_eksi_alan'] = df_beam_only['Kiriş_eksi_alan']

# Floor elemanlarının Beton_Guncel değerini güncelle
floor_mask = df_new['ObjectType'] == 'Floor'
df_floor_only = df_new[floor_mask].copy()

for idx, row in df_floor_only.iterrows():
    story = row['Story']
    story_beam_mask = (df_new['Story'] == story) & (df_new['ObjectType'] == 'Beam')
    story_wall_mask = (df_new['Story'] == story) & (df_new['ObjectType'] == 'Wall')
    kiris_eksi_alan = df_new.loc[story_beam_mask, 'Kiriş_eksi_alan'].sum()
    perde_eksi_alan = df_new.loc[story_wall_mask, 'Perde_eksi_alan'].sum()
    df_new.loc[idx, 'Beton_Guncel'] = row['Beton_Guncel'] - kiris_eksi_alan - perde_eksi_alan

# ObjectType değerlerini Türkçeleştir
df_new['ObjectType'] = df_new['ObjectType'].replace({
    'Column': 'Kolon',
    'Beam': 'Kiriş',
    'Wall': 'Perde',
    'Floor': 'Döşeme'
})

# ObjectType sütununda "All" olan satırları sil
df_new = df_new[df_new['ObjectType'] != 'All']

# Sütun isimlerini değiştir
df_new = df_new.rename(columns={
    'Story': 'Kat',
    'ObjectType': 'Eleman',
    'Beton_Guncel': 'Beton (m3)'
})

# ObjectType bazında Beton_Guncel toplamlarını hesapla ve sütun isimlerini güncelle
df_summary_by_element = df_new.groupby('Eleman')['Beton (m3)'].sum().reset_index()

# Kat bazında Beton_Guncel toplamlarını hesapla
df_summary_by_story = df_new.groupby('Kat')['Beton (m3)'].sum().reset_index()

# Genel toplam Beton_Guncel değerini hesapla
total_beton_guncel = df_new['Beton (m3)'].sum()

# 3D Model için gerekli hazırlıklar
# Convert point data to numeric for plotting
numeric_cols = ['X', 'Y', 'Z']
for col in numeric_cols:
    if col in df_point.columns:
        df_point[col] = pd.to_numeric(df_point[col], errors='coerce')

# Create mappings for wall thickness
section_thickness_map = {}
for _, prop in df_wall_prop.iterrows():
    if 'Name' in prop and 'Thickness' in prop:
        try:
            section_thickness_map[prop['Name']] = float(prop['Thickness'])
        except (ValueError, TypeError):
            st.warning(f"Could not convert thickness value for section {prop['Name']}")
            section_thickness_map[prop['Name']] = 0.3  # Default thickness

# Create a mapping of wall names/labels to section properties
wall_section_map = {}
for _, area in df_area_sections.iterrows():
    if 'PropType' in area and area['PropType'] == 'Wall':
        identifier = None
        for id_col in ['UniqueName', 'Label']:
            if id_col in area and pd.notna(area[id_col]):
                identifier = area[id_col]
                break
        
        if identifier and 'SectProp' in area:
            wall_section_map[identifier] = area['SectProp']

# Create mappings for floor (slab) thickness
slab_thickness_map = {}
for _, prop in df_slab_props.iterrows():
    if 'Name' in prop and 'Thickness' in prop:
        try:
            slab_thickness_map[prop['Name']] = float(prop['Thickness'])
        except (ValueError, TypeError):
            st.warning(f"Could not convert thickness value for slab section {prop['Name']}")
            slab_thickness_map[prop['Name']] = 0.2  # Default thickness

# Create a mapping of floor names to section properties
floor_section_map = {}
for _, area in df_area_sections.iterrows():
    if 'PropType' in area and area['PropType'] == 'Slab':
        identifier = None
        for id_col in ['UniqueName', 'Label']:
            if id_col in area and pd.notna(area[id_col]):
                identifier = area[id_col]
                break
        
        if identifier and 'SectProp' in area:
            floor_section_map[identifier] = area['SectProp']

# Create mappings for frame (beam and column) dimensions (width and height/depth)
frame_dimensions_map = {}
for _, prop in df_frame_props.iterrows():
    if 'Name' in prop and 't2' in prop and 't3' in prop:
        try:
            frame_dimensions_map[prop['Name']] = {
                'height': float(prop['t3']),  # t3 is height for beams, depth for columns
                'width': float(prop['t2'])    # t2 is width for both beams and columns
            }
        except (ValueError, TypeError):
            st.warning(f"Could not convert dimensions for frame section {prop['Name']}")
            frame_dimensions_map[prop['Name']] = {'height': 0.4, 'width': 0.4}  # Default dimensions

# Create a mapping of frame (beam and column) names to section properties
frame_section_map = {}
for _, frame in df_frame_sections.iterrows():
    identifier = None
    for id_col in ['UniqueName', 'Label']:
        if id_col in frame and pd.notna(frame[id_col]):
            identifier = frame[id_col]
            break
    
    if identifier and 'SectProp' in frame:
        frame_section_map[identifier] = frame['SectProp']

# Selectbox ve kullanıcı arayüzü oluştur
st.write("### Metraj ve 3D Model")

# Selectbox ile seçenekleri sun
option = st.selectbox(
    "Metraj Türünü Seçin:",
    ["Eleman ve Kat Bazında Metraj", "Eleman Bazında Metraj", "Kat Bazında Metraj", "Toplam Metraj"]
)

# Streamlit session state ile 3D modelin yalnızca bir kez oluşturulmasını sağlayalım
if 'fig' not in st.session_state:
    st.session_state.fig = None
    st.session_state.model_rendered = False

# Metraj Tablosu (Hesapla butonu olmadan doğrudan gösterim)
st.write("#### Seçilen Metraj Türü")
if option == "Eleman ve Kat Bazında Metraj":
    st.dataframe(df_new[['Kat', 'Eleman', 'Beton (m3)']], use_container_width=True)
elif option == "Eleman Bazında Metraj":
    st.dataframe(df_summary_by_element, use_container_width=True)
elif option == "Kat Bazında Metraj":
    st.dataframe(df_summary_by_story, use_container_width=True)
elif option == "Toplam Metraj":
    st.write(f"Toplam Beton (m³): **{total_beton_guncel:.2f}**")

# 3D Model oluşturma için ayrı bir buton (isteğe bağlı olarak bırakıyorum)
if st.button("3D Modeli Oluştur"):
    if not st.session_state.model_rendered:
        st.write("### 3D Model Görselleştirme")
        with st.spinner("3D model oluşturuluyor..."):
            # Create a 3D figure
            fig = go.Figure()

            # Fixed settings
            opacity = 1
            wall_color = "#A9A9A9"
            beam_color = "#A9A9A9"
            column_color = "#A9A9A9"
            floor_color = "#A9A9A9"

            # Helper function to create 3D mesh for walls
            def create_wall_mesh(pt1, pt2, pt3, pt4, thickness=0.3):
                p1 = np.array([float(pt1['X']), float(pt1['Y']), float(pt1['Z'])])
                p2 = np.array([float(pt2['X']), float(pt2['Y']), float(pt2['Z'])])
                p3 = np.array([float(pt3['X']), float(pt3['Y']), float(pt3['Z'])])
                p4 = np.array([float(pt4['X']), float(pt4['Y']), float(pt4['Z'])])
                
                v1 = p2 - p1
                v2 = p4 - p1
                normal = np.cross(v1, v2)
                normal = normal / np.linalg.norm(normal) * thickness/2
                
                front_p1, front_p2, front_p3, front_p4 = p1 + normal, p2 + normal, p3 + normal, p4 + normal
                back_p1, back_p2, back_p3, back_p4 = p1 - normal, p2 - normal, p3 - normal, p4 - normal
                
                vertices = [
                    front_p1, front_p2, front_p3, front_p4,
                    back_p1, back_p2, back_p3, back_p4
                ]
                
                i, j, k, l, m, n, o, p = 0, 1, 2, 3, 4, 5, 6, 7
                faces = [
                    [i, j, k], [i, k, l],
                    [m, o, n], [m, p, o],
                    [i, l, p], [i, p, m],
                    [j, n, k], [j, n, o],
                    [k, o, p], [k, p, l],
                    [i, m, n], [i, n, j]
                ]
                
                x = [v[0] for v in vertices]
                y = [v[1] for v in vertices]
                z = [v[2] for v in vertices]
                
                I, J, K = [], [], []
                for face in faces:
                    I.append(face[0])
                    J.append(face[1])
                    K.append(face[2])
                
                return x, y, z, I, J, K

            # Helper function to create floor mesh from points
            def create_floor_mesh(point_ids, df_point, thickness=0.2):
                coords = []
                for pt_id in point_ids:
                    row = df_point.loc[df_point['UniqueName'] == pt_id]
                    if row.empty:
                        raise ValueError(f"Point {pt_id} not found in df_point.")
                    x = float(row['X'].iloc[0])
                    y = float(row['Y'].iloc[0])
                    z = float(row['Z'].iloc[0])
                    coords.append(np.array([x, y, z]))

                if len(coords) < 3:
                    raise ValueError("At least 3 points are needed to form a floor mesh.")

                coords = np.array(coords)
                centroid = np.mean(coords, axis=0)
                vectors = coords - centroid
                angles = np.arctan2(vectors[:,1], vectors[:,0])
                sort_idx = np.argsort(angles)
                coords_sorted = coords[sort_idx]

                if len(coords_sorted) >= 3:
                    v1 = coords_sorted[1] - coords_sorted[0]
                    v2 = coords_sorted[2] - coords_sorted[0]
                    normal = np.cross(v1, v2)
                    norm_len = np.linalg.norm(normal)
                    if norm_len > 1e-12:
                        normal = normal / norm_len
                    else:
                        normal = np.array([0, 0, 1])
                else:
                    normal = np.array([0, 0, 1])

                normal = normal * (thickness / 2.0)
                top_points = coords_sorted + normal
                bottom_points = coords_sorted - normal
                vertices = np.concatenate((top_points, bottom_points), axis=0)

                n = len(coords_sorted)
                x = [v[0] for v in vertices]
                y = [v[1] for v in vertices]
                z = [v[2] for v in vertices]

                I, J, K = [], [], []
                for i in range(1, n - 1):
                    I.append(0)
                    J.append(i)
                    K.append(i + 1)

                for i in range(n + 1, 2*n - 1):
                    I.append(n)
                    J.append(i + 1)
                    K.append(i)

                for i in range(n):
                    i_next = (i + 1) % n
                    top_i = i
                    top_i_next = i_next
                    bot_i = n + i
                    bot_i_next = n + i_next
                    I.append(top_i)
                    J.append(top_i_next)
                    K.append(bot_i)
                    I.append(top_i_next)
                    J.append(bot_i_next)
                    K.append(bot_i)

                return x, y, z, I, J, K

            # Add walls with dynamic thickness
            for _, wall in df_wall.iterrows():
                try:
                    pt1_id = wall['UniquePt1']
                    pt2_id = wall['UniquePt2']
                    pt3_id = wall['UniquePt3']
                    pt4_id = wall['UniquePt4']
                    
                    pt1 = df_point[df_point['UniqueName'] == pt1_id].iloc[0]
                    pt2 = df_point[df_point['UniqueName'] == pt2_id].iloc[0]
                    pt3 = df_point[df_point['UniqueName'] == pt3_id].iloc[0]
                    pt4 = df_point[df_point['UniqueName'] == pt4_id].iloc[0]
                    
                    wall_thickness = 0.3
                    wall_identifiers = []
                    for id_col in ['UniqueName', 'WallBay', 'Label']:
                        if id_col in wall and pd.notna(wall[id_col]):
                            wall_identifiers.append(wall[id_col])
                    
                    section_name = None
                    for identifier in wall_identifiers:
                        if identifier in wall_section_map:
                            section_name = wall_section_map[identifier]
                            break
                    
                    if section_name and section_name in section_thickness_map:
                        wall_thickness = section_thickness_map[section_name]
                        
                    x, y, z, I, J, K = create_wall_mesh(pt1, pt2, pt3, pt4, thickness=wall_thickness)
                    
                    fig.add_trace(go.Mesh3d(
                        x=x, y=y, z=z,
                        i=I, j=J, k=K,
                        color=wall_color,
                        opacity=opacity,
                        name=f'Wall {wall["UniqueName"]} (t={wall_thickness}m)'
                    ))
                    
                except (IndexError, KeyError) as e:
                    st.warning(f"Error creating wall {wall['UniqueName']}: {e}")
                    continue

            # Add floors with dynamic thickness
            if 'UniqueName' in df_floor.columns:
                grouped_floors = df_floor.groupby('UniqueName')
                
                for unique_name, floor_group in grouped_floors:
                    try:
                        point_ids = []
                        for _, floor in floor_group.iterrows():
                            for i in range(1, 20):
                                pt_col = f'UniquePt{i}'
                                if pt_col in floor_group.columns and not pd.isna(floor.get(pt_col)) and floor.get(pt_col) != "None":
                                    point_id = floor[pt_col]
                                    if point_id not in point_ids:
                                        point_ids.append(point_id)
                        
                        if len(point_ids) < 3:
                            st.warning(f"Floor {unique_name} has fewer than 3 points ({len(point_ids)}). Skipping.")
                            continue
                            
                        floor_thickness = 0.2
                        floor_identifiers = [unique_name]
                        if 'FloorBay' in floor_group.columns and pd.notna(floor_group['FloorBay'].iloc[0]):
                            floor_identifiers.append(floor_group['FloorBay'].iloc[0])
                        
                        section_name = None
                        for identifier in floor_identifiers:
                            if identifier in floor_section_map:
                                section_name = floor_section_map[identifier]
                                break
                        
                        if section_name and section_name in slab_thickness_map:
                            floor_thickness = slab_thickness_map[section_name]
                        
                        x, y, z, I, J, K = create_floor_mesh(point_ids, df_point, thickness=floor_thickness)
                        
                        fig.add_trace(go.Mesh3d(
                            x=x, y=y, z=z,
                            i=I, j=J, k=K,
                            color=floor_color,
                            opacity=opacity,
                            name=f'Floor {unique_name} (t={floor_thickness}m)'
                        ))
                    except Exception as e:
                        st.warning(f"Error creating floor {unique_name}: {e}")
                        continue

            # Add beams with dynamic dimensions
            for _, beam in df_beam.iterrows():
                try:
                    start_point = beam['UniquePtI']
                    end_point = beam['UniquePtJ']
                    
                    start_coords = df_point[df_point['UniqueName'] == start_point].iloc[0]
                    end_coords = df_point[df_point['UniqueName'] == end_point].iloc[0]
                    
                    start = np.array([float(start_coords['X']), float(start_coords['Y']), float(start_coords['Z'])])
                    end = np.array([float(end_coords['X']), float(end_coords['Y']), float(end_coords['Z'])])
                    
                    # Get beam dimensions from section properties
                    beam_width = 0.25  # Default width (t3)
                    beam_height = 0.5  # Default height (t2)
                    
                    # Try getting the beam section from different possible identifying columns
                    beam_identifiers = [beam['UniqueName']]
                    if 'BeamBay' in beam and pd.notna(beam['BeamBay']):
                        beam_identifiers.append(beam['BeamBay'])
                    
                    # Look up section property for this beam
                    section_name = None
                    for identifier in beam_identifiers:
                        if identifier in frame_section_map:
                            section_name = frame_section_map[identifier]
                            break
                    
                    # If we found a section name, get its dimensions
                    if section_name and section_name in frame_dimensions_map:
                        beam_height = frame_dimensions_map[section_name]['height']  # t2
                        beam_width = frame_dimensions_map[section_name]['width']    # t3
                    
                    direction = end - start
                    length = np.linalg.norm(direction)
                    if length > 0:
                        unit_direction = direction / length
                    else:
                        continue
                    
                    if abs(unit_direction[0]) < abs(unit_direction[1]):
                        perp1 = np.array([1, 0, 0])
                    else:
                        perp1 = np.array([0, 1, 0])
                        
                    perp1 = perp1 - np.dot(perp1, unit_direction) * unit_direction
                    perp1 = perp1 / np.linalg.norm(perp1) * beam_width/2
                    
                    perp2 = np.cross(unit_direction, perp1)
                    perp2 = perp2 / np.linalg.norm(perp2) * beam_height/2
                    
                    v1 = start + perp1 + perp2
                    v2 = start - perp1 + perp2
                    v3 = start - perp1 - perp2
                    v4 = start + perp1 - perp2
                    v5 = end + perp1 + perp2
                    v6 = end - perp1 + perp2
                    v7 = end - perp1 - perp2
                    v8 = end + perp1 - perp2
                    
                    vertices = [v1, v2, v3, v4, v5, v6, v7, v8]
                    
                    i, j, k, l, m, n, o, p = 0, 1, 2, 3, 4, 5, 6, 7
                    faces = [
                        [i, j, k], [i, k, l],
                        [m, n, o], [m, o, p],
                        [i, m, p], [i, p, l],
                        [j, n, o], [j, o, k],
                        [i, m, n], [i, n, j],
                        [l, p, o], [l, o, k]
                    ]
                    
                    x = [v[0] for v in vertices]
                    y = [v[1] for v in vertices]
                    z = [v[2] for v in vertices]
                    
                    I, J, K = [], [], []
                    for face in faces:
                        I.append(face[0])
                        J.append(face[1])
                        K.append(face[2])
                    
                    fig.add_trace(go.Mesh3d(
                        x=x, y=y, z=z,
                        i=I, j=J, k=K,
                        color=beam_color,
                        opacity=opacity,
                        name=f'Beam {beam["UniqueName"]} (w={beam_width}m, h={beam_height}m)'
                    ))
                except (IndexError, KeyError) as e:
                    st.warning(f"Error creating beam {beam['UniqueName']}: {e}")
                    continue

            # Add columns with dynamic dimensions
            for _, column in df_column.iterrows():
                try:
                    start_point = column['UniquePtI']
                    end_point = column['UniquePtJ']
                    
                    start_coords = df_point[df_point['UniqueName'] == start_point].iloc[0]
                    end_coords = df_point[df_point['UniqueName'] == end_point].iloc[0]
                    
                    start = np.array([float(start_coords['X']), float(start_coords['Y']), float(start_coords['Z'])])
                    end = np.array([float(end_coords['X']), float(end_coords['Y']), float(end_coords['Z'])])
                    
                    # Get column dimensions from section properties
                    column_width = 0.4  # Default width (t3)
                    column_depth = 0.4  # Default depth (t2)
                    
                    # Try getting the column section from different possible identifying columns
                    column_identifiers = [column['UniqueName']]
                    if 'ColumnBay' in column and pd.notna(column['ColumnBay']):
                        column_identifiers.append(column['ColumnBay'])
                    
                    # Look up section property for this column
                    section_name = None
                    for identifier in column_identifiers:
                        if identifier in frame_section_map:
                            section_name = frame_section_map[identifier]
                            break
                    
                    # If we found a section name, get its dimensions
                    if section_name and section_name in frame_dimensions_map:
                        column_depth = frame_dimensions_map[section_name]['height']  # t2 (depth for columns)
                        column_width = frame_dimensions_map[section_name]['width']   # t3 (width for columns)
                    
                    half_width = column_width / 2
                    half_depth = column_depth / 2
                    
                    v1 = start + np.array([half_width, half_depth, 0])
                    v2 = start + np.array([-half_width, half_depth, 0])
                    v3 = start + np.array([-half_width, -half_depth, 0])
                    v4 = start + np.array([half_width, -half_depth, 0])
                    
                    height_vector = end - start
                    v5 = v1 + height_vector
                    v6 = v2 + height_vector
                    v7 = v3 + height_vector
                    v8 = v4 + height_vector
                    
                    vertices = [v1, v2, v3, v4, v5, v6, v7, v8]
                    
                    i, j, k, l, m, n, o, p = 0, 1, 2, 3, 4, 5, 6, 7
                    faces = [
                        [i, j, k], [i, k, l],
                        [m, n, o], [m, o, p],
                        [i, m, p], [i, p, l],
                        [j, n, o], [j, o, k],
                        [i, m, n], [i, n, j],
                        [l, p, o], [l, o, k]
                    ]
                    
                    x = [v[0] for v in vertices]
                    y = [v[1] for v in vertices]
                    z = [v[2] for v in vertices]
                    
                    I, J, K = [], [], []
                    for face in faces:
                        I.append(face[0])
                        J.append(face[1])
                        K.append(face[2])
                    
                    fig.add_trace(go.Mesh3d(
                        x=x, y=y, z=z,
                        i=I, j=J, k=K,
                        color=column_color,
                        opacity=opacity,
                        name=f'Column {column["UniqueName"]} (w={column_width}m, d={column_depth}m)'
                    ))
                except (IndexError, KeyError) as e:
                    st.warning(f"Error creating column {column['UniqueName']}: {e}")
                    continue

            # Update layout
            fig.update_layout(
                title="ETABS 3D Model",
                scene=dict(
                    xaxis_title='X (m)',
                    yaxis_title='Y (m)',
                    zaxis_title='Z (m)',
                    aspectmode='data',
                    camera=dict(
                        eye=dict(x=1.8, y=1.8, z=0.8)
                    )
                ),
                height=800,
                margin=dict(l=0, r=0, b=0, t=30)
            )

            # 3D modeli session state'e kaydet
            st.session_state.fig = fig
            st.session_state.model_rendered = True

# 3D Modeli her zaman göster (eğer oluşturulmuşsa)
if st.session_state.fig is not None:
    st.write("### 3D Model Görselleştirme")
    st.plotly_chart(st.session_state.fig, use_container_width=True)

# Görsel iyileştirme için biraz boşluk ekleyelim
st.markdown("<br>", unsafe_allow_html=True)

comtypes.CoUninitialize()