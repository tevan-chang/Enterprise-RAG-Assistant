import { Sparkles } from "lucide-react";

export const metadata = {
  title: "隱私權政策 | Enterprise AI Knowledge & Report Assistant",
};

export default function PrivacyPolicyPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-12">
      <div className="flex items-center gap-3">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-sm">
          <Sparkles className="size-6" />
        </span>
        <div>
          <h1 className="text-xl font-bold text-foreground">Enterprise AI Knowledge & Report Assistant</h1>
          <p className="text-sm text-muted-foreground">隱私權政策</p>
        </div>
      </div>

      <section className="flex flex-col gap-6 text-sm leading-relaxed text-foreground">
        <p className="text-muted-foreground">最後更新日期：2026 年 9 月 18 日</p>

        <div className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">關於本服務</h2>
          <p>
            Enterprise AI Knowledge & Report Assistant（以下稱「本服務」）是一套供企業內部使用者上傳文件、
            進行檢索式問答（RAG）與報表查詢的知識助手系統。本頁面說明本服務蒐集哪些個人資料、如何使用，
            以及如何與我們聯絡。
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">我們蒐集的資料</h2>
          <ul className="list-disc space-y-1 pl-5">
            <li>帳號資訊：登入用電子郵件信箱、租戶（部門/組織）與角色。</li>
            <li>使用者上傳的文件內容（PDF、XLSX）及其衍生的文字片段與向量嵌入。</li>
            <li>使用者在 Chat／Report 功能中輸入的查詢內容，以及系統產生的回覆。</li>
            <li>系統操作紀錄（如文件處理狀態、API 使用量），用於功能運作與異常追蹤。</li>
          </ul>
        </div>

        <div className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">資料使用方式</h2>
          <ul className="list-disc space-y-1 pl-5">
            <li>提供文件檢索、問答與報表統計等核心功能。</li>
            <li>透過電子郵件（Gmail API）通知使用者文件處理結果或需要人工複核的異動。</li>
            <li>系統錯誤監控與服務品質改善（Sentry）。</li>
          </ul>
          <p>
            本服務不會將使用者資料用於本服務以外的商業行銷用途，亦不會對外公開販售。
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">第三方服務</h2>
          <p>本服務於運作過程中會使用以下第三方服務處理資料，各自受其自身隱私權政策規範：</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>OpenAI（文字生成與向量嵌入）</li>
            <li>Supabase（資料庫、身份驗證與檔案儲存）</li>
            <li>Google（Gmail API，用於寄送系統通知信）</li>
          </ul>
        </div>

        <div className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">資料保存與刪除</h2>
          <p>
            使用者上傳的文件與衍生資料，會保存至該文件被使用者或管理員自本服務刪除為止。
            如需刪除帳號或相關資料，請透過下方聯絡方式與我們聯繫。
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">聯絡我們</h2>
          <p>
            如對本隱私權政策或您的資料有任何疑問，歡迎透過電子郵件與我們聯絡：
            <a href="mailto:tevan090726@gmail.com" className="ml-1 text-primary underline underline-offset-2">
              tevan090726@gmail.com
            </a>
          </p>
        </div>
      </section>
    </main>
  );
}
