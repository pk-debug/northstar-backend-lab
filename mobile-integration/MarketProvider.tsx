/** Network-backed replacement for the existing marketData.ts global fixture. */
import {createContext,useCallback,useContext,useEffect,useMemo,useState,type PropsWithChildren} from 'react';
import type {MarketAsset} from '../market/types';
import {getAssets,getIndexes,type Index} from './stockApi';

type MarketContextValue={assets:MarketAsset[];indexes:Index[];loading:boolean;error:string|null;refresh:()=>Promise<void>;findAsset:(symbol:string)=>MarketAsset|undefined};
const MarketContext=createContext<MarketContextValue|null>(null);
export function MarketProvider({children}:PropsWithChildren){
  const [assets,setAssets]=useState<MarketAsset[]>([]);
  const [indexes,setIndexes]=useState<Index[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState<string|null>(null);
  /** React rerenders any subscribed screen after a successful refresh. */
  const refresh=useCallback(async()=>{
    setLoading(true);
    try {const [a,i]=await Promise.all([getAssets(),getIndexes()]);setAssets(a);setIndexes(i);setError(null);}
    catch(e){setError(e instanceof Error?e.message:'Market connection failed');}
    finally{setLoading(false);}
  },[]);
  useEffect(()=>{void refresh();},[refresh]);
  const findAsset=useCallback((symbol:string)=>assets.find(a=>a.symbol===symbol.toUpperCase()),[assets]);
  const value=useMemo(()=>({assets,indexes,loading,error,refresh,findAsset}),[assets,indexes,loading,error,refresh,findAsset]);
  return <MarketContext.Provider value={value}>{children}</MarketContext.Provider>;
}
export function useMarket(){const value=useContext(MarketContext);if(!value)throw new Error('useMarket requires MarketProvider');return value;}
