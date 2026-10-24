/** Server-owned replacement for src/features/trading/TradingProvider.tsx.
 * This intentionally changes placeOrder() to return a Promise<OrderResult>.
 */
import {createContext,useCallback,useContext,useEffect,useMemo,useState,type PropsWithChildren} from 'react';
import type {Position,SimulatedOrder} from '../market/types';
import {getOrders,getPortfolio,placeOrder as submitOrder,type OrderRequest,type OrderResult} from './stockApi';

type TradingContextValue={cash:number;positions:Position[];orders:SimulatedOrder[];loading:boolean;error:string|null;refresh:()=>Promise<void>;placeOrder:(request:OrderRequest,key?:string)=>Promise<OrderResult>};
const TradingContext=createContext<TradingContextValue|null>(null);
/** Random request keys make each new intent unique; keep one key for retries. */
const newKey=()=>`${Date.now()}-${Math.random().toString(36).slice(2)}`;
export function BackendTradingProvider({children}:PropsWithChildren){
  const [cash,setCash]=useState(0);
  const [positions,setPositions]=useState<Position[]>([]);
  const [orders,setOrders]=useState<SimulatedOrder[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState<string|null>(null);
  const refresh=useCallback(async()=>{
    setLoading(true);
    try{
      const [portfolio,activity]=await Promise.all([getPortfolio(),getOrders()]);
      setCash(portfolio.cash);setPositions(portfolio.positions);setOrders(activity);setError(null);
    }catch(e){setError(e instanceof Error?e.message:'Portfolio connection failed');}
    finally{setLoading(false);}
  },[]);
  useEffect(()=>{void refresh();},[refresh]);
  const placeOrder=useCallback(async(request:OrderRequest,key?:string):Promise<OrderResult>=>{
    try{
      const result=await submitOrder(request,key??newKey());
      // A committed order succeeded even if the later UI refresh fails.
      await refresh();
      return result;
    }catch(e){return {ok:false,message:e instanceof Error?e.message:'Network failure: check Activity before retrying'};}
  },[refresh]);
  const value=useMemo(()=>({cash,positions,orders,loading,error,refresh,placeOrder}),[cash,positions,orders,loading,error,refresh,placeOrder]);
  return <TradingContext.Provider value={value}>{children}</TradingContext.Provider>;
}
export function useTrading(){const value=useContext(TradingContext);if(!value)throw new Error('useTrading requires BackendTradingProvider');return value;}
