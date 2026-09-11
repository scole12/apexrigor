"""All positive forecast examples are synthetic and must remain off production."""
import copy,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
from _mma_forecast_contract import forecast_status,positions_sha256,validated_card,validated_positions

def fixture():
    positions=[]
    for market,selection,line,price,probability,tier in [('WINNER','SYNTHETIC Fighter A',None,-110,.57,'MODERATE'),('METHOD','SYNTHETIC Fighter A by submission',None,220,.35,'WEAK')]:
        positions.append({'bout_id':'synthetic-bout','matchup':'SYNTHETIC Fighter A vs SYNTHETIC Fighter B','fighter_a':'SYNTHETIC Fighter A','fighter_b':'SYNTHETIC Fighter B','market':market,'selection':selection,'line':line,'price':price,'probability':probability,'tier':tier,'sportsbook':'FanDuel','rationale':'SYNTHETIC TEST ONLY. This is not a real forecast. This text tests detailed rationale rendering. The numbers are test data. No athlete is evaluated here. Nothing from this test may be published or emailed.','trace':{'issuance_id':'synthetic-issuance','model_sha256':'a'*64}})
    return {'picks_published':True,'release_state':'SEALED_RELEASE_AVAILABLE','active_model':'SYNTHETIC_TEST_ONLY','active_model_sha256':'a'*64,'issuance_id':'synthetic-issuance','issuance_status':'SEALED','fight_count':1,'card':[{'bout_id':'synthetic-bout','official_display_order':1,'fighter_a':'SYNTHETIC Fighter A','fighter_b':'SYNTHETIC Fighter B'}],'positions':positions,'positions_sha256':positions_sha256(positions),'t2':{'status':'ISSUED','scheduled_utc':'2026-09-05T14:00:00Z'}}

class MmaForecastContractTests(unittest.TestCase):
    def test_preserves_every_field_and_full_rationale(self):
        s=fixture();p=validated_positions(s)
        self.assertEqual(p,s['positions']);self.assertIsNot(p,s['positions'])
        self.assertEqual(len(p),2)
    def test_no_release_has_no_fake_positions(self):
        self.assertEqual(validated_positions({'positions':[],'picks_published':False}),[])
    def test_published_but_empty_is_rejected(self):
        with self.assertRaises(ValueError):validated_positions({'positions':[],'picks_published':True})
    def test_no_release_cannot_publish_fixture(self):
        s=fixture();s['release_state']='NO_RELEASE_SCIENTIFIC_GATE'
        with self.assertRaises(ValueError):validated_positions(s)
    def test_nonexact_sealed_state_cannot_publish_fixture(self):
        s=fixture();s['release_state']='SEALED_RELEASE_NO_EVENT_ISSUANCE'
        with self.assertRaises(ValueError):validated_positions(s)
    def test_market_outside_joint_marginals_is_rejected_not_filtered(self):
        s=fixture();s['positions'][1]['market']='DURATION';s['positions_sha256']=positions_sha256(s['positions'])
        with self.assertRaisesRegex(ValueError,'allowed joint marginal'):validated_positions(s)
    def test_every_required_field_is_checked(self):
        for field in ['bout_id','matchup','fighter_a','fighter_b','market','selection','rationale','price','probability','tier','sportsbook']:
            s=fixture();del s['positions'][0][field];s['positions_sha256']=positions_sha256(s['positions'])
            with self.subTest(field=field),self.assertRaises(ValueError):validated_positions(s)
    def test_tampered_probability_cannot_silently_render(self):
        s=fixture();s['positions'][0]['probability']=.99
        with self.assertRaises(ValueError):validated_positions(s)
    def test_duplicate_position_is_rejected(self):
        s=fixture();s['positions'].append(copy.deepcopy(s['positions'][0]));s['positions_sha256']=positions_sha256(s['positions'])
        with self.assertRaises(ValueError):validated_positions(s)
    def test_foreign_issuance_is_rejected(self):
        s=fixture();s['positions'][0]['trace']['issuance_id']='different';s['positions_sha256']=positions_sha256(s['positions'])
        with self.assertRaises(ValueError):validated_positions(s)
    def test_wrong_model_is_rejected(self):
        s=fixture();s['active_model_sha256']='b'*64
        with self.assertRaises(ValueError):validated_positions(s)
    def test_failed_t2_is_not_pending(self):
        s={'t2':{'status':'FAIL_CLOSED_NO_SCIENTIFIC_RELEASE','scheduled_utc':'2026-09-05T14:00:00Z'}}
        self.assertEqual(forecast_status(s,[])['code'],'NO_FORECASTS_ISSUED')
    def test_future_t2_remains_pending(self):
        s={'t2':{'status':'SCHEDULED','scheduled_utc':'2026-09-12T14:00:00Z'}}
        self.assertEqual(forecast_status(s,[],datetime(2026,9,5,tzinfo=timezone.utc))['code'],'AWAITING_T2')
    def test_after_t2_is_not_mislabelled_as_pending(self):
        s={'t2':{'status':'SCHEDULED','scheduled_utc':'2026-09-05T14:00:00Z'}}
        self.assertEqual(forecast_status(s,[],datetime(2026,9,5,15,tzinfo=timezone.utc))['code'],'NO_FORECASTS_ISSUED')
    def test_numeric_invalid_values_are_rejected(self):
        for value in [True,-.1,1.1,'57%']:
            s=fixture();s['positions'][0]['probability']=value;s['positions_sha256']=positions_sha256(s['positions'])
            with self.subTest(value=value),self.assertRaises(ValueError):validated_positions(s)
    def test_official_display_order_must_be_unique_and_contiguous(self):
        state={'fight_count':3,'card':[{'official_display_order':1,'fighter_a':'A','fighter_b':'B'},{'official_display_order':2,'fighter_a':'C','fighter_b':'D'},{'official_display_order':3,'fighter_a':'E','fighter_b':'F'}]}
        self.assertEqual(validated_card(state),state['card'])
        for orders in ([1,2,2],[1,2,4],[1,2,True]):
            bad=copy.deepcopy(state)
            for bout,order in zip(bad['card'],orders):bout['official_display_order']=order
            with self.subTest(orders=orders),self.assertRaises(ValueError):validated_card(bad)
        bad=copy.deepcopy(state);bad['fight_count']=True
        with self.assertRaises(ValueError):validated_card(bad)
    def test_position_must_match_one_official_card_pair(self):
        s=fixture();s['positions'][0]['fighter_b']='SYNTHETIC Fighter C';s['positions_sha256']=positions_sha256(s['positions'])
        with self.assertRaisesRegex(ValueError,'official-card fighter pair'):validated_positions(s)
    def test_time_is_an_allowed_joint_marginal(self):
        s=fixture();s['positions'][1]['market']='TIME';s['positions'][1]['selection']='Round 3';s['positions_sha256']=positions_sha256(s['positions'])
        self.assertEqual(validated_positions(s)[1]['market'],'TIME')

if __name__=='__main__':unittest.main()
