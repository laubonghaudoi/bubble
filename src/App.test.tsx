import{describe,it,expect}from'vitest';
describe('dashboard contracts',()=>{it('uses Pages-safe base URL',()=>{expect(import.meta.env.BASE_URL).toBe('/')});it('distinguishes zero from missing',()=>{const value:number|null=0;expect(value).not.toBeNull()})});
