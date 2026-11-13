import copy
import unittest
from routing.routing import plan


class RoutingTests(unittest.TestCase):
    def setUp(self):
        # Fictional IDs: fixtures are not provider model availability claims.
        self.prefs={'crew.strider1':['Sol','Opus']}
        self.catalog={'Sol':dict(verified=True,model='fixture-codex',provider='codex',runtime='codex'),
                      'Opus':dict(verified=True,model='fixture-claude',provider='claude',runtime='claude-code')}
        self.status={p:dict(admission_open=True,active_permits=[]) for p in ('codex','claude')}
        self.ready={'codex':True,'claude-code':True}
    def runplan(self, **kw):
        return plan('crew.strider1',self.prefs,self.catalog,self.status,self.ready,**kw)
    def test_first_verified_exact_mapping(self):
        result=self.runplan()
        self.assertEqual(result['selected']['model'],'fixture-codex')
        self.assertTrue(result['ready_to_launch'])
    def test_unknown_no_alias_guessing(self):
        self.prefs['crew.strider1']=['sol','Fable 5.2']
        result=self.runplan()
        self.assertEqual(result['status'],'blocked')
        self.assertTrue(all(x['reason']=='unknown_preference_id' for x in result['skipped']))
    def test_empty_catalog_blocks(self):
        self.catalog.clear()
        self.assertEqual(self.runplan()['status'],'blocked')
    def test_invalid_catalog_runtime_mismatch(self):
        for update in ({'runtime':'claude-code'},{'verified':False},{'model':''},{'provider':'unknown'},{'provider':[]},{'runtime':{}}):
            old=copy.deepcopy(self.catalog)
            self.catalog['Sol'].update(update)
            self.assertEqual(self.runplan()['selected']['preference'],'Opus')
            self.catalog=old
    def test_closed_provider_falls_back(self):
        self.status['codex']['admission_open']=False
        result=self.runplan()
        self.assertEqual(result['selected']['provider'],'claude')
        self.assertEqual(result['skipped'][0]['reason'],'provider_closed')
    def test_any_active_seat_waits_even_closed_provider(self):
        self.status['claude'].update(admission_open=False,active_permits=[{'seat':'crew.strider1'}])
        self.assertEqual(self.runplan()['status'],'wait')
    def test_other_seat_does_not_hold(self):
        self.status['claude']['active_permits']=[{'seat':'crew.other'}]
        self.assertEqual(self.runplan()['status'],'selected')
    def test_unready_harness_fallback_or_block(self):
        self.ready['codex']=False
        self.assertEqual(self.runplan()['selected']['provider'],'claude')
        self.ready['claude-code']=1
        self.assertEqual(self.runplan()['status'],'blocked')
    def test_unknown_provider_status_blocks(self):
        del self.status['claude']
        self.assertEqual(self.runplan()['status'],'blocked')
    def test_malformed_active_permit_blocks(self):
        self.status['claude']['active_permits']=[{}]
        self.assertEqual(self.runplan()['status'],'blocked')
    def test_inquisitor_has_no_implicit_preference(self):
        result=plan('crew.inquisitor',self.prefs,self.catalog,self.status,self.ready)
        self.assertEqual(result['reason'],'seat_preference_missing')
    def test_handover_requires_exact_stopped_session_and_durable_checkpoint(self):
        current=dict(session_id='old',model='old-model',provider='codex',runtime='codex')
        good=dict(session_id='old',stopped=True,checkpoint=dict(reference='artifact:checkpoint-1',durable=True))
        for proof in (None,{},dict(good,stopped=False),dict(good,session_id='other'),dict(good,checkpoint={'reference':'temporary'})):
            result=self.runplan(current=current,handover=proof)
            self.assertEqual(result['status'],'handover_required')
            self.assertFalse(result['ready_to_launch'])
        self.assertTrue(self.runplan(current=current,handover=good)['ready_to_launch'])
    def test_unchanged_route_no_handover(self):
        current=dict(session_id='old',**{k:self.catalog['Sol'][k] for k in ('model','provider','runtime')})
        self.assertEqual(self.runplan(current=current)['status'],'selected')
    def test_inputs_not_mutated(self):
        inputs=copy.deepcopy((self.prefs,self.catalog,self.status,self.ready))
        self.runplan()
        self.assertEqual(inputs,(self.prefs,self.catalog,self.status,self.ready))

if __name__=='__main__':unittest.main()
