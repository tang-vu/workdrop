import React from 'react'
type Props={size?:number}
const wrap=(body:React.ReactNode)=>(p:Props)=><svg width={p.size||22} height={p.size||22} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{body}</svg>
export const ArrowRight=wrap(<path d="M4 12h16M14 6l6 6-6 6"/>)
export const ArrowUpRight=wrap(<path d="M5 19 19 5M8 5h11v11"/>)
export const ChevronRight=wrap(<path d="m9 5 7 7-7 7"/>)
export const Check=wrap(<path d="m4 12 5 5L20 6"/>)
export const Download=wrap(<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>)
export const Film=wrap(<><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4"/></>)
export const Menu=wrap(<path d="M4 7h16M4 12h16M4 17h16"/>)
export const Plus=wrap(<path d="M12 4v16M4 12h16"/>)
export const RefreshCw=wrap(<path d="M20 11a8 8 0 0 0-14-5L4 8M4 4v4h4M4 13a8 8 0 0 0 14 5l2-2M20 20v-4h-4"/>)
export const Wallet=wrap(<><rect x="3" y="6" width="18" height="15" rx="2"/><path d="M3 9V5a2 2 0 0 1 2-2h13M16 14h5"/></>)
export const X=wrap(<path d="M5 5 19 19M19 5 5 19"/>)
export const CircleHelp=wrap(<><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4.2 1.8c-1.2 1-1.7 1.3-1.7 3M12 17h.01"/></>)
export const ShoppingBag=wrap(<path d="M4 8h16l-1 13H5L4 8ZM9 8V6a3 3 0 0 1 6 0v2"/>)
export const Sparkles=wrap(<path d="m12 2 2.2 7.8L22 12l-7.8 2.2L12 22l-2.2-7.8L2 12l7.8-2.2L12 2Z"/>)
