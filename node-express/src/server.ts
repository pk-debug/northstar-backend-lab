/** Express HTTP boundary: request validation and conversion to stable mobile DTOs. */
import express from 'express';
import cors from 'cors';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { z } from 'zod';
import { createStore, initialize, type Row, type Store } from './db.js';

// Bundled market fixture is sourced from the actual React Native app.
type Asset = {symbol:string;companyName:string;exchange:string;price:number;priceCents:number;change:number;changePercent:number;history:number[];category:string};
const assets = JSON.parse(fs.readFileSync(path.resolve(process.cwd(),'../shared/market-assets.json'),'utf8')) as Asset[];
const indexes = JSON.parse(fs.readFileSync(path.resolve(process.cwd(),'../shared/market-indexes.json'),'utf8'));
const market = new Map(assets.map(a=>[a.symbol,a]));
const visible = ({priceCents: _private, ...asset}: Asset) => asset;
const orderSchema = z.strictObject({symbol:z.string().min(1).max(16).transform(x=>x.trim().toUpperCase()),side:z.enum(['BUY','SELL']),quantity:z.number().int().positive().max(1000000)});

class ApiError extends Error {
  /** Domain exceptions carry both HTTP status and friendly OrderResult message. */
  constructor(public status: number, message: string) { super(message); }
}
const cents = (value: unknown): number => Number(value);
/** Keep new/old orders identical when replaying idempotent requests. */
function orderDto(r: Row) {
  return { id:r.id, symbol:r.symbol,side:r.side,quantity:Number(r.quantity),price:cents(r.price_cents)/100,createdAt:r.created_at,status:r.status };
}

async function start() {
  const db: Store = createStore();
  await initialize(db);
  const app = express();
  app.use(express.json({limit:'16kb'}));
  app.use(cors()); // demo only; restrict allowed origins in production.
  app.get('/health', (_req,res)=>res.json({status:'ok',service:'node-express'}));
  app.get('/api/v1/assets', (req,res)=>{
    const q = String(req.query.q??'').trim().toLowerCase();
    res.json(assets.filter(a=>a.symbol.toLowerCase().includes(q)||a.companyName.toLowerCase().includes(q)).map(visible));
  });
  app.get('/api/v1/assets/:symbol', (req,res)=>{
    const asset = market.get(String(req.params.symbol).toUpperCase());
    if (!asset) { res.status(404).json({ok:false,message:'That asset is not available in the sample market.'}); return; }
    res.json(visible(asset));
  });
  app.get('/api/v1/indexes', (_req,res)=>res.json(indexes));
  app.get('/api/v1/portfolio', async (_req,res,next)=>{
    try {
      const [account] = await db.rows('SELECT cash_cents FROM accounts WHERE id=1');
      const rows = await db.rows('SELECT * FROM positions ORDER BY symbol');
      const positions = rows.map(r=>({symbol:r.symbol,quantity:Number(r.quantity),averageCost:cents(r.average_cost_cents)/100}));
      const positionsValue = positions.reduce((n,p)=>n+(market.get(String(p.symbol))?.priceCents??0)*p.quantity,0);
      const cash = cents(account.cash_cents);
      res.json({cash:cash/100,positions,positionsValue:positionsValue/100,totalValue:(cash+positionsValue)/100});
    } catch(err){next(err);}
  });
  app.get('/api/v1/orders',async (_req,res,next)=>{
    try {res.json((await db.rows('SELECT * FROM orders ORDER BY created_at DESC,id DESC')).map(orderDto));}catch(err){next(err);}
  });
  app.post('/api/v1/orders',async (req,res,next)=>{
    try {
      const parsed = orderSchema.safeParse(req.body);
      if (!parsed.success) throw new ApiError(400,'Enter a known symbol, BUY/SELL, and a positive whole-share quantity.');
      const {symbol,side,quantity} = parsed.data;
      const key = req.header('Idempotency-Key')?.trim();
      if (!key || !/^[a-zA-Z0-9._:-]{1,128}$/.test(key)) throw new ApiError(400,'Supply an Idempotency-Key of 1–128 safe characters.');
      const asset = market.get(symbol);
      if (!asset) throw new ApiError(404,'That asset is not available in the sample market.');
      const result = await db.transaction(async tx => {
        // A row lock serializes competing orders on PostgreSQL; BEGIN IMMEDIATE on SQLite.
        const pg = !!process.env.DATABASE_URL?.startsWith('postgres');
        const [account] = await tx.rows('SELECT cash_cents FROM accounts WHERE id=1'+(pg?' FOR UPDATE':''));
        const [prior] = await tx.rows('SELECT * FROM orders WHERE idempotency_key=?',[key]);
        if(prior){
          if(prior.symbol!==symbol || prior.side!==side || Number(prior.quantity)!==quantity)
            throw new ApiError(409,'Idempotency-Key was already used for a different order.');
          return {code:200,body:{ok:true,order:orderDto(prior)}};
        }
        const [pos] = await tx.rows('SELECT * FROM positions WHERE symbol=?',[symbol]);
        const amount=asset.priceCents*quantity, cash=cents(account.cash_cents);
        if(side==='BUY' && amount>cash) throw new ApiError(409,'There is not enough demo cash for this order.');
        if(side==='SELL' && (!pos||Number(pos.quantity)<quantity)) throw new ApiError(409,'You do not own enough shares for this demo sale.');
        if(side==='BUY') {
          if(pos){
            const newQuantity=Number(pos.quantity)+quantity;
            const avg=Math.floor((cents(pos.average_cost_cents)*Number(pos.quantity)+amount+Math.floor(newQuantity/2))/newQuantity);
            await tx.exec('UPDATE positions SET quantity=?,average_cost_cents=? WHERE symbol=?',[newQuantity,avg,symbol]);
          } else await tx.exec('INSERT INTO positions(symbol,quantity,average_cost_cents) VALUES(?,?,?)',[symbol,quantity,asset.priceCents]);
        } else {
          const remain=Number(pos.quantity)-quantity;
          if(!remain) await tx.exec('DELETE FROM positions WHERE symbol=?',[symbol]);
          else await tx.exec('UPDATE positions SET quantity=? WHERE symbol=?',[remain,symbol]);
        }
        await tx.exec('UPDATE accounts SET cash_cents=? WHERE id=1',[side==='BUY'?cash-amount:cash+amount]);
        const order={id:randomUUID(),symbol,side,quantity,price:asset.priceCents/100,createdAt:new Date().toISOString(),status:'SIMULATED'};
        await tx.exec('INSERT INTO orders(id,idempotency_key,symbol,side,quantity,price_cents,created_at,status) VALUES(?,?,?,?,?,?,?,?)', [order.id,key,symbol,side,quantity,asset.priceCents,order.createdAt,order.status]);
        return {code:201,body:{ok:true,order}};
      });
      res.status(result.code).json(result.body);
    }catch(err){next(err);}
  });
  app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction)=>{
    if(err instanceof ApiError) {res.status(err.status).json({ok:false,message:err.message});return;}
    console.error(err); res.status(500).json({ok:false,message:'Internal server error'});
  });
  const port=Number(process.env.PORT || 3000);
  app.listen(port,()=>console.log(`Northstar Node listening on http://localhost:${port}`));
}
start().catch(err=>{console.error(err);process.exitCode=1;});
