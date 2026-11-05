"use client";

import { PlusIcon } from "lucide-react";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";

export function NewChatButton() {
  const pathname = usePathname() ?? "/";
  if (!pathname.startsWith("/s/")) {
    return null;
  }

  return (
    <Button onClick={() => window.location.assign("/")} size="sm" type="button" variant="ghost">
      <PlusIcon />
      <span className="max-sm:sr-only">New chat</span>
    </Button>
  );
}
