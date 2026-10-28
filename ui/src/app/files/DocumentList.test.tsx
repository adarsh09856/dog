import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
const mocks=vi.hoisted(()=>({list:vi.fn()}));
vi.mock('@/client/sdk.gen',()=>({listDocumentsApiV1KnowledgeBaseDocumentsGet:mocks.list,deleteDocumentApiV1KnowledgeBaseDocumentsDocumentUuidDelete:vi.fn()}));
vi.mock('@/hooks/useOrganizationTimezone',()=>({useOrganizationTimezone:()=> 'Asia/Kolkata'}));
vi.mock('./DocumentEditor',()=>({default:()=>null,isEditableDocument:()=>true}));
import DocumentList from './DocumentList';
afterEach(cleanup);
it('surfaces resolved API errors and supports retry',async()=>{
    mocks.list.mockResolvedValueOnce({error:{detail:'Storage service unavailable'}}).mockResolvedValue({data:{documents:[]}});
    render(<DocumentList refreshTrigger={0}/>);
    expect((await screen.findByRole('alert')).textContent).toContain('Storage service unavailable');
    fireEvent.click(screen.getByRole('button',{name:'Retry'}));
    await screen.findByPlaceholderText('Search documents...');
    expect(screen.queryByRole('alert')).toBeNull();
});
