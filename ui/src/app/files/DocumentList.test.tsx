import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
const mocks=vi.hoisted(()=>({list:vi.fn()}));
vi.mock('@/client/sdk.gen',()=>({deleteDocumentApiV1KnowledgeBaseDocumentsDocumentUuidDelete:vi.fn()}));
vi.mock('@/lib/kodewavesApi',()=>({apiFetch:mocks.list}));
vi.mock('@/hooks/useOrganizationTimezone',()=>({useOrganizationTimezone:()=> 'Asia/Kolkata'}));
vi.mock('./DocumentEditor',()=>({default:()=>null,isEditableDocument:()=>true}));
import DocumentList from './DocumentList';
afterEach(cleanup);
it('surfaces resolved API errors and supports retry',async()=>{
    mocks.list.mockRejectedValueOnce(new Error('Storage service unavailable')).mockResolvedValue({documents:[],total:0,limit:100,offset:0});
    render(<DocumentList refreshTrigger={0}/>);
    expect((await screen.findByRole('alert')).textContent).toContain('Storage service unavailable');
    fireEvent.click(screen.getByRole('button',{name:'Retry'}));
    await screen.findByPlaceholderText('Search documents...');
    expect(screen.queryByRole('alert')).toBeNull();
});
