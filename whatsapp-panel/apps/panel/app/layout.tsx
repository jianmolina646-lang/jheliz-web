import'./styles.css';import type{Metadata}from'next';
export const metadata:Metadata={title:'Jheliz WhatsApp Control',robots:{index:false,follow:false}};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="es"><body>{children}</body></html>}
