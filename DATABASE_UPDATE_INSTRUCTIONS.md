# Instruksi untuk Update Database

## Langkah 1: Jalankan Script SQL
Jalankan script `add_billing_id_column.sql` di database PostgreSQL Anda:

```bash
psql -U magna -d support_ticket_db -f add_billing_id_column.sql
```

Atau copy-paste script SQL ke PostgreSQL client Anda.

## Langkah 2: Restart Server
Restart FastAPI server untuk memuat perubahan kode:

```bash
uvicorn main:app --reload
```

## Langkah 3: Test Endpoint
Test endpoint baru untuk memastikan response sudah benar:

```bash
# Test get projects for user
curl -X GET "http://localhost:8000/users/project/USER_123456" \
  -H "accept: application/json"

# Expected response:
[
  {
    "project_id": "PROJ_12345",
    "billing_id": "BILLING_123"
  },
  {
    "project_id": "PROJ_67890", 
    "billing_id": "BILLING_456"
  }
]
```

## Perubahan yang Telah Dilakukan:

1. **Database Schema**: 
   - Menambahkan kolom `billing_id` ke tabel `user_projects`
   - Menambahkan index untuk performa yang lebih baik

2. **Response Model**: 
   - Mengubah response dari `List[str]` menjadi `List[UserProjectResponse]`
   - `UserProjectResponse` berisi `project_id` dan `billing_id`

3. **Fungsi yang Diupdate**:
   - `get_projects_for_user()` - Sekarang mengembalikan project_id dan billing_id
   - `add_user_to_project()` - Menyimpan billing_id saat menambahkan user ke project
   - `add_users_to_group()` - Menyimpan billing_id saat menambahkan user ke grup
   - `add_projects_to_group()` - Menyimpan billing_id saat menambahkan project ke grup

4. **Backward Compatibility**:
   - Script SQL akan mengupdate data yang sudah ada dengan billing_id yang sesuai
   - Semua fungsi existing tetap berfungsi normal