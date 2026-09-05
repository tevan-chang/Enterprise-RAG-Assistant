-- 修正：本地 GoTrue（v2.196.0）的 Admin createUser API 實測不會把 request body 的
-- app_metadata 合併進 auth.users.raw_app_meta_data（即使官方文件範例就是這樣用），
-- 導致 handle_new_user trigger 在 tenant_id/role 為 NOT NULL 時直接讓整個
-- 使用者建立失敗（violates not-null constraint）——實務上一律得先建立使用者，
-- 再用 admin.updateUserById() 補設 app_metadata（會觸發 on_auth_user_metadata_updated
-- 補上正確值）。放寬成 nullable 不影響安全性：後端 get_current_user()（見 ADR 0004）
-- 本來就不查這張表做授權判斷，只在 JWT 本身缺 tenant_id/role claim 時已經會拒絕請求。
alter table public.profiles alter column tenant_id drop not null;
alter table public.profiles alter column role drop not null;
