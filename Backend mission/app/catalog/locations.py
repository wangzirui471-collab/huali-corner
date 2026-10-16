"""Public meeting-point choices transcribed from supplied campus screenshots."""
BUILDING_GROUPS = [
    {'name': '本科楼栋（截图候选）', 'buildings': ['C1', 'C2', 'C3', 'C4', 'B9', 'B4', 'B3', 'B2', 'D1', 'C8', 'C7', 'C6', 'C5']},
    {'name': '其他已有楼栋（待核实）', 'buildings': ['本科综合楼', '行政楼', 'L17', 'L18', 'G1主楼', 'G1副楼', 'G2', 'G3',
        'G4主楼', 'G4副楼', 'A1', 'A2', 'A3', 'A4', 'L16', 'L13', 'L12', 'L11', 'L10', 'L9', 'L8', 'L7', 'L4',
        'L3', 'L2', 'L1', 'L5', 'L6', 'L15', '7号楼仓库', 'D2', 'D6', 'D5']},
]
BUILDINGS = [building for group in BUILDING_GROUPS for building in group['buildings']]
