"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  BarChart3, 
  MessageSquare, 
  Calendar, 
  FileText, 
  LogOut,
  SlidersHorizontal
} from "lucide-react";
import { cn } from "@/lib/utils";

const menuItems = [
  { icon: MessageSquare, label: "Review Pulse", href: "/" },
  { icon: FileText, label: "Mutual Fund FAQs", href: "/faqs" },
  { icon: Calendar, label: "Scheduled Appointments", href: "/appointments" },
  { icon: SlidersHorizontal, label: "Meeting Slot Configuration", href: "/holidays" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="w-64 border-r border-white/10 h-screen flex flex-col bg-[#0A0A0A] fixed left-0 top-0 z-50">
      <div className="p-6">
        <div className="flex items-center gap-3 mb-10">
          <div className="w-10 h-10 bg-neon-green rounded-lg flex items-center justify-center text-black">
            <BarChart3 size={24} strokeWidth={2.5} />
          </div>
          <div>
            <div className="text-white font-bold text-sm leading-tight">Internal Ops</div>
            <div className="text-white/40 text-[10px] uppercase tracking-wider font-semibold">Operations Console</div>
          </div>
        </div>
        
        <div className="text-white/20 text-[11px] uppercase tracking-widest font-bold mb-4 px-2">Workspace</div>
        
        <nav className="space-y-1">
          {menuItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.label}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-all duration-200 group",
                  isActive 
                    ? "bg-white/5 text-white" 
                    : "text-white/50 hover:bg-white/5 hover:text-white"
                )}
              >
                <item.icon size={18} className={cn(isActive ? "text-neon-green" : "group-hover:text-white")} />
                <span className="text-sm font-medium">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
      
      <div className="mt-auto p-6 border-t border-white/5">
        <div className="flex items-center gap-3 px-3 py-2 text-white/40 hover:text-white cursor-pointer transition-colors group">
          <LogOut size={18} className="group-hover:text-white" />
          <span className="text-sm font-medium">Logout</span>
        </div>
      </div>
    </div>
  );
}
