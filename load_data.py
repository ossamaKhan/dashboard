import os
import sys
import django
import pandas as pd
from decimal import Decimal, InvalidOperation

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')
django.setup()

from marketing.models import SiteData

FILE_PATH = r'F:\dashboard\marketing.xlsx'  # 👈 change this
def to_dec(val):
    try:
        if pd.isna(val): return None
        cleaned = str(val).replace(',', '').replace(' ', '').strip()
        if cleaned in ('', '-', '—', 'nan', 'None'): return None
        return Decimal(cleaned)
    except: return None

def to_int(val):
    try:
        if pd.isna(val): return None
        cleaned = str(val).replace(',', '').replace(' ', '').strip()
        if cleaned in ('', '-', '—', 'nan', 'None'): return None
        return int(float(cleaned))
    except: return None

def to_float(val):
    try:
        if pd.isna(val): return None
        return float(val)
    except: return None

def to_str(val):
    try:
        if pd.isna(val): return None
        s = str(val).strip()
        return None if s in ('', 'nan', 'None') else s
    except: return None

print("Reading Excel file...")
df = pd.read_excel(FILE_PATH, header=None)  # no header — read raw

# The REAL headers are row 0, data starts from row 1
# But since headers after col 19 are broken, we skip header row manually
df.columns = range(len(df.columns))  # name columns 0,1,2...47
df = df.iloc[1:].reset_index(drop=True)  # skip header row, start from data

# Filter out any row where col 0 (Franchise) is 'Franchise' or NaN
df = df[df[0].notna()]
df = df[df[0] != 'Franchise']

print(f"Total rows to upload: {len(df)}")

# Column index mapping based on your exact header order:
# 0:Franchise, 1:Month, 2:Key, 3:2G ID, 4:3G ID, 5:4G ID,
# 6:Technology, 7:Business Unit, 8:Region, 9:Commercial District,
# 10:CL Status, 11:USF/Non-USF, 12:latitude, 13:longitude,
# 14:PTA District, 15:Site Status, 16:Type, 17:Feb'26, 18:ARM,
# 19:FCA, 20:BVS, 21:ACT_90D, 22:ACT_30D, 23:ACT_90D_4G,
# 24:HVC_BASE, 25:TOT_REVN_AMT, 26:BVS_RETAILER, 27:EVC_RETAILER,
# 28:Minutes_Outgoing, 29:Minutes_Incoming, 30:Volume_GBs,
# 31:DATA_NTWRK_VOL_4G, 32:FCA_Adjusted, 33:Tot_Revival,
# 34:Gross_Churn, 35:Net_Add, 36:AVG_DLY_ACT, 37:Act_Recharger,
# 38:M0_Revn, 39:MNP_FCA, 40:HANDSET_4G, 41:RCHRG_FACE_VALUE_MTD,
# 42:PP_RECHAR_FACE_VAL_MTD, 43:PREPAID_DGTL_AMOUNT,
# 44:POSTPAID_DGTL_AMOUNT, 45:CONVENTIONAL_RECHARGE,
# 46:TOTAL_RECHARGE, 47:DIGI_RECHARGE

objects = []
for i, row in df.iterrows():
    obj = SiteData(
        franchise               = to_str(row[0]),
        month                   = to_int(row[1]),
        key                     = to_int(row[2]),
        id_2g                   = to_str(row[3]),
        id_3g                   = to_str(row[4]),
        id_4g                   = to_str(row[5]),
        technology              = to_str(row[6]),
        business_unit           = to_str(row[7]),
        region                  = to_str(row[8]),
        commercial_district     = to_str(row[9]),
        cl_status               = to_str(row[10]),
        usf_status              = to_str(row[11]),
        latitude                = to_float(row[12]),
        longitude               = to_float(row[13]),
        pta_district            = to_str(row[14]),
        site_status             = to_str(row[15]),
        site_type               = to_str(row[16]),
        feb_26                  = to_str(row[17]),
        arm                     = to_str(row[18]),
        fca                     = to_dec(row[19]),
        bvs                     = to_dec(row[20]),
        act_90d                 = to_int(row[21]),
        act_30d                 = to_int(row[22]),
        act_90d_4g              = to_int(row[23]),
        hvc_base                = to_int(row[24]),
        tot_revn_amt            = to_dec(row[25]),
        bvs_retailer            = to_int(row[26]),
        evc_retailer            = to_int(row[27]),
        minutes_outgoing        = to_dec(row[28]),
        minutes_incoming        = to_dec(row[29]),
        volume_gbs              = to_dec(row[30]),
        data_ntwrk_vol_4g       = to_dec(row[31]),
        fca_adjusted            = to_dec(row[32]),
        tot_revival             = to_int(row[33]),
        gross_churn             = to_int(row[34]),
        net_add                 = to_int(row[35]),
        avg_dly_act             = to_dec(row[36]),
        act_recharger           = to_int(row[37]),
        m0_revn                 = to_dec(row[38]),
        mnp_fca                 = to_int(row[39]),
        handset_4g              = to_int(row[40]),
        rchrg_face_value_mtd    = to_dec(row[41]),
        pp_rechar_face_val_mtd  = to_dec(row[42]),
        prepaid_dgtl_amount     = to_dec(row[43]),
        postpaid_dgtl_amount    = to_dec(row[44]),
        conventional_recharge   = to_dec(row[45]),
        total_recharge          = to_dec(row[46]),
        digi_recharge           = to_dec(row[47]),
    )
    objects.append(obj)

    if len(objects) == 500:
        SiteData.objects.bulk_create(objects)
        print(f"✅ Uploaded {i+1} rows...")
        objects = []

if objects:
    SiteData.objects.bulk_create(objects)

print(f"\n🎉 Done! {len(df)} records uploaded.")

# Sanity check
sample = SiteData.objects.first()
print(f"\nSanity check:")
print(f"  franchise:    {sample.franchise}")
print(f"  tot_revn_amt: {sample.tot_revn_amt}")
print(f"  act_90d:      {sample.act_90d}")
print(f"  net_add:      {sample.net_add}")
print(f"  total_recharge: {sample.total_recharge}")