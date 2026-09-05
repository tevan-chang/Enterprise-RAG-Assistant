import Link from "next/link";

import { SignOutButton } from "@/components/sign-out-button";

export default function Home() {
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Enterprise AI Knowledge & Report Assistant</h1>
        <SignOutButton />
      </div>
      <div className="flex gap-4 text-sm">
        <Link href="/documents/upload" className="text-primary underline-offset-4 hover:underline">
          上傳文件
        </Link>
        <Link href="/documents" className="text-primary underline-offset-4 hover:underline">
          文件列表
        </Link>
        <Link href="/chat" className="text-primary underline-offset-4 hover:underline">
          知識問答
        </Link>
      </div>
    </main>
  );
}
