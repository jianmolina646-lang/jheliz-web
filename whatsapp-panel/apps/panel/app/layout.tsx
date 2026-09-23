import'./styles.css';import'./qr.css';import'./store.css';import'./store-auth.css';import'./premium-store.css';import'./typography.css';import'./admin.css';import'./admin-v2.css';import type{Metadata}from'next';
export const metadata:Metadata={title:'Jheliz Digital | Cuentas completas de streaming',description:'Tienda de cuentas completas de streaming con entrega digital.',robots:{index:true,follow:true}};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="es"><body>{children}</body></html>}
