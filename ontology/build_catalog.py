"""Rebuild the engineering-only ontology catalog. No legal corpus is downloaded.

The declarations below are the editable source for catalog.json and module Turtle.
This is a schema proposal, not a legally reviewed model of Turkish law.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NS = "https://lawyer-assistant.local/ontology/"
VERSION = "0.1.0"
PREFIX = """@prefix la: <https://lawyer-assistant.local/ontology/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

"""

# Each row is id | English label | superclass. Types are not institution instances.
MODULES = {
    "foundation": ("shared", """
Entity|Entity|
LegalEntity|Legal entity|Entity
SchemaCategory|Schema category|Entity
LegalDomain|Legal domain|SchemaCategory
LegalConcept|Legal concept|SchemaCategory
DefinedTerm|Defined term|LegalConcept
RoleType|Role type|SchemaCategory
AgentType|Agent type|SchemaCategory
EventType|Event type|SchemaCategory
FactPattern|Abstract fact pattern|SchemaCategory
Identifier|Identifier|Entity
TimeInterval|Time interval|Entity
Jurisdiction|Jurisdiction|LegalEntity
TerritorialArea|Territorial area|Entity
Agent|Agent instance|LegalEntity
NaturalPerson|Natural person|Agent
LegalPerson|Legal person|Agent
ParticipantRole|Participant role instance|Entity
Event|Event instance|Entity
MonetaryAmount|Monetary amount|Entity
ReferenceTable|Versioned reference table|Entity
ReferenceValue|Effective reference value|Entity
"""),
    "norms": ("structure", """
InstrumentType|Legal instrument type|SchemaCategory
LegalInstrument|Legal instrument identity|LegalEntity
InstrumentVersion|Legal instrument version|LegalEntity
Provision|Stable provision identity|LegalEntity
ProvisionVersion|Provision text version|LegalEntity
TextSubdivision|Textual subdivision|LegalEntity
Article|Article subdivision|TextSubdivision
Paragraph|Paragraph subdivision|TextSubdivision
Subparagraph|Subparagraph subdivision|TextSubdivision
PublicationEvent|Publication event|Event
EnactmentEvent|Enactment event|Event
AmendmentEvent|Amendment event|Event
RepealEvent|Repeal event|Event
AnnulmentEvent|Annulment event|Event
TransitionalRule|Transitional rule|LegalEntity
LegislativeProposal|Legislative proposal|LegalEntity
LegislativeProceeding|Legislative proceeding|LegalEntity
LegislativeReason|Legislative reason|LegalEntity
Consolidation|Consolidated representation|LegalEntity
TreatyInstrument|Treaty instrument|LegalInstrument
HistoricalPredecessor|Continuity-relevant predecessor|LegalEntity
"""),
    "institutions": ("structure", """
InstitutionType|Institution type|SchemaCategory
Institution|Institution instance|Agent
OrganizationalUnit|Organizational unit instance|Institution
Court|Court instance|Institution
CourtChamber|Court chamber instance|OrganizationalUnit
JudicialCouncil|Judicial council instance|Institution
LegislativeBody|Legislative body instance|Institution
ExecutiveBody|Executive body instance|Institution
AdministrativeAuthority|Administrative authority instance|Institution
Regulator|Regulator instance|AdministrativeAuthority
ProfessionalBody|Professional body instance|Institution
EnforcementOffice|Enforcement office instance|Institution
DisputeResolutionBody|Dispute resolution body instance|Institution
InstitutionalChange|Institutional change event|Event
CompetenceAssignment|Qualified competence assignment|LegalEntity
CompetenceRestriction|Competence restriction|LegalEntity
JurisdictionRule|Jurisdiction rule|LegalEntity
ReviewRoute|Review or appeal route|LegalEntity
"""),
    "legal_positions": ("structure", """
NormativeRule|Conditional normative rule|LegalEntity
LegalPosition|Legal position|LegalEntity
Right|Right|LegalPosition
Obligation|Obligation|LegalPosition
Prohibition|Prohibition|LegalPosition
Permission|Permission|LegalPosition
LegalPower|Legal power|LegalPosition
Immunity|Immunity|LegalPosition
Liability|Liability|LegalPosition
LegalCondition|Legal condition|LegalEntity
LegalElement|Legal element|LegalCondition
Exception|Exception|LegalCondition
Consequence|Legal consequence|LegalEntity
Remedy|Remedy|Consequence
Sanction|Sanction|Consequence
ContractType|Contract type|SchemaCategory
ClauseType|Contract clause type|SchemaCategory
ContractualPosition|Contractual legal position|LegalPosition
"""),
    "procedures": ("structure", """
ProcedureType|Procedure type|SchemaCategory
Procedure|Procedure definition|LegalEntity
ProceduralStage|Procedural stage|LegalEntity
ProceduralRequirement|Procedural requirement|LegalEntity
ProceduralAct|Procedural act|Event
DeadlineRule|Conditional deadline rule|LegalEntity
DeadlineTrigger|Deadline trigger|LegalEntity
TimeComputationRule|Time computation rule|LegalEntity
ProofBurden|Burden of proof|LegalEntity
ProofStandard|Standard of proof|LegalEntity
AdmissibilityCondition|Admissibility condition|LegalCondition
EvidenceCategory|Evidence category|SchemaCategory
AlternativeDisputeResolution|Alternative dispute resolution procedure|Procedure
"""),
    "jurisprudence": ("jurisprudence", """
Proceeding|Proceeding identity|LegalEntity
ProceedingStage|Actual proceeding stage|LegalEntity
JudicialDecision|Judicial decision identity|LegalEntity
DecisionVersion|Decision text version|LegalEntity
DecisionType|Decision type|SchemaCategory
Panel|Deciding panel|Agent
Opinion|Opinion|LegalEntity
Dissent|Dissenting opinion|Opinion
LegalIssue|Legal issue|LegalEntity
PartyArgument|Party argument|LegalEntity
AllegedFact|Alleged fact|LegalEntity
JudicialFinding|Judicial factual finding|LegalEntity
Holding|Judicial legal proposition|LegalEntity
Disposition|Disposition|LegalEntity
CitationOccurrence|Textual citation occurrence|LegalEntity
UnresolvedReference|Unresolved citation or version|LegalEntity
AuthorityTreatment|Qualified authority treatment|LegalEntity
ApplicabilityAssessment|Qualified applicability assessment|LegalEntity
ConflictAssessment|Qualified conflict assessment|LegalEntity
TrendHypothesis|Jurisprudential trend hypothesis|LegalEntity
EditorialAnnotation|Editorial annotation|LegalEntity
"""),
    "evidence": ("shared", """
SourceArtifact|Immutable source artifact|Entity
SourceRepresentation|Source representation|Entity
EvidencePassage|Exact evidence passage|Entity
Assertion|Evidenced relationship assertion|Entity
LegalReview|Legal review record|Entity
Derivation|Inference derivation|Entity
ExtractionRun|Extraction run|Entity
GraphSnapshot|Immutable graph snapshot|Entity
SourceCollection|Source collection|Entity
CoverageRecord|Coverage observation|Entity
RightsRecord|Rights and permitted-use record|Entity
"""),
    "private_overlay": ("shared", """
Matter|Private legal matter|Entity
MatterDocument|Private matter document|Entity
MatterFact|Private matter fact|Entity
MatterEvent|Private matter event|Event
MatterAssertion|Private matter assertion|Assertion
MatterParty|Private matter party|Agent
WorkProduct|Private work product|Entity
WorkProductVersion|Work product version|Entity
Claim|Work-product claim|Entity
LawyerCorrection|Scoped lawyer correction|Entity
ReviewDecision|Work-product review decision|Entity
"""),
}

# id | domain | range | module | requires legal review | meaning
RELATIONS = """
instanceOf|Entity|SchemaCategory|foundation|false|An instance belongs to a category; never a subclass assertion.
inDomain|Entity|LegalDomain|foundation|false|Categorized within an engineering legal-domain taxonomy.
hasRole|Agent|ParticipantRole|foundation|false|Participation role in a qualified context.
roleType|ParticipantRole|RoleType|foundation|false|Type of a particular participant role.
hasParticipant|Event|Agent|foundation|false|An event participant, with roles qualified separately.
occursIn|Event|TerritorialArea|foundation|false|Location of an event, not a jurisdiction conclusion.
patternOf|FactPattern|EventType|foundation|true|Reviewed abstraction of an event pattern.
definedBy|DefinedTerm|ProvisionVersion|foundation|true|A term definition in an exact text version.
conceptRelatedTo|LegalConcept|LegalConcept|foundation|true|Conceptual relationship, not identity or precedence.
hasReferenceValue|ReferenceTable|ReferenceValue|foundation|true|A structured value whose effective interval is separately evidenced.
containsProvision|LegalInstrument|Provision|norms|false|Stable provision containment.
hasInstrumentVersion|LegalInstrument|InstrumentVersion|norms|false|Instrument-to-version identity link.
hasProvisionVersion|Provision|ProvisionVersion|norms|false|Provision-to-version identity link; does not select latest.
versionOf|LegalEntity|LegalEntity|norms|false|Version identity, distinct from legal succession.
hasSubdivision|LegalEntity|TextSubdivision|norms|false|Text structure, not normative hierarchy.
publishedIn|LegalEntity|PublicationEvent|norms|false|Publication event, distinct from commencement.
enactedBy|LegalInstrument|Institution|norms|true|Enacting authority based on source evidence.
amends|AmendmentEvent|Provision|norms|true|An amendment event affects a provision.
createsVersion|AmendmentEvent|ProvisionVersion|norms|true|An amendment creates an evidenced text version.
repeals|RepealEvent|LegalEntity|norms|true|Repeal with separately evidenced legal effect dates.
annuls|AnnulmentEvent|LegalEntity|norms|true|Annulment with separately evidenced scope and effect dates.
replaces|LegalEntity|LegalEntity|norms|true|Legal replacement is distinct from textual similarity.
renumbers|Provision|Provision|norms|true|Continuity under a changed provision number.
splitsFrom|Provision|Provision|norms|true|A provision originates from part of another.
mergesFrom|Provision|Provision|norms|true|A provision combines earlier provisions.
hasTransitionRule|LegalEntity|TransitionalRule|norms|true|Transition applicability requires rule interpretation.
hasLegislativeReason|Provision|LegislativeReason|norms|false|Linked legislative history is not enacted text.
consolidates|Consolidation|InstrumentVersion|norms|false|Consolidated representation of a specified version.
predecessorOf|HistoricalPredecessor|LegalEntity|norms|true|Earlier material retained for continuity or applicable law.
influencedBy|LegalEntity|LegalEntity|norms|true|Historical influence does not create present authority.
organizationalPartOf|Institution|Institution|institutions|true|Organization only, not appeal or legal superiority.
establishedBy|Institution|ProvisionVersion|institutions|true|Legal basis for institution establishment.
renamedFrom|Institution|Institution|institutions|true|Institutional naming continuity.
successorOf|Institution|Institution|institutions|true|Institutional succession, not identical powers.
abolishedBy|Institution|InstitutionalChange|institutions|true|Institution abolition event.
heldBy|CompetenceAssignment|Institution|institutions|true|Holder of a qualified competence.
authorizedBy|LegalEntity|ProvisionVersion|institutions|true|Exact legal basis of authority.
coversSubject|CompetenceAssignment|LegalConcept|institutions|true|Subject-matter competence qualifier.
coversTerritory|CompetenceAssignment|TerritorialArea|institutions|true|Territorial competence qualifier.
coversProcedure|CompetenceAssignment|Procedure|institutions|true|Procedural competence qualifier.
restrictedBy|CompetenceAssignment|CompetenceRestriction|institutions|true|Restriction on competence.
routeFrom|ReviewRoute|Institution|institutions|true|Origin of a qualified review route.
routeTo|ReviewRoute|Institution|institutions|true|Destination of a qualified review route.
supervisedBy|Institution|Institution|institutions|true|Supervision is not appellate review.
createdBy|LegalPosition|ProvisionVersion|legal_positions|true|Legal basis of a conditional position.
heldByRole|LegalPosition|RoleType|legal_positions|true|Abstract holder role, not an identified client.
owedByRole|Obligation|RoleType|legal_positions|true|Abstract obliged role with conditions separately recorded.
requiresCondition|LegalEntity|LegalCondition|legal_positions|true|A condition required for applicability.
hasElement|NormativeRule|LegalElement|legal_positions|true|Element of a normative rule.
subjectToException|LegalEntity|Exception|legal_positions|true|Exception whose scope requires interpretation.
hasConsequence|NormativeRule|Consequence|legal_positions|true|Conditional legal consequence.
remediedBy|LegalPosition|Remedy|legal_positions|true|Potential remedy, not a guaranteed result.
expressedBy|NormativeRule|ProvisionVersion|legal_positions|true|Interpretive representation of a source provision.
hasClauseType|ContractType|ClauseType|legal_positions|false|Schema-level contract clause classification.
hasStage|Procedure|ProceduralStage|procedures|true|Stage within a procedural definition.
requiresStep|ProceduralStage|ProceduralRequirement|procedures|true|Procedural prerequisite.
triggeredBy|DeadlineRule|DeadlineTrigger|procedures|true|Deadline trigger, not an assumed matter date.
computedBy|DeadlineRule|TimeComputationRule|procedures|true|Reviewed time computation rule.
subjectToDeadline|LegalEntity|DeadlineRule|procedures|true|Applicable deadline relationship.
requiresProofOf|ProofBurden|LegalElement|procedures|true|An element requiring proof.
usesProofStandard|ProofBurden|ProofStandard|procedures|true|Qualified standard rather than an unconditional rule.
hasAdmissibilityCondition|Procedure|AdmissibilityCondition|procedures|true|Condition for procedural admissibility.
decidedIn|JudicialDecision|Proceeding|jurisprudence|false|Decision-to-proceeding identity.
issuedBy|JudicialDecision|Institution|jurisprudence|false|Issuing body, distinct from appellate status.
decidedByPanel|JudicialDecision|Panel|jurisprudence|false|Recorded deciding panel.
issuedAtStage|JudicialDecision|ProceedingStage|jurisprudence|false|Actual proceeding stage.
hasDecisionVersion|JudicialDecision|DecisionVersion|jurisprudence|false|Decision-to-source-version identity.
hasOpinion|JudicialDecision|Opinion|jurisprudence|false|Opinion is not necessarily the court holding.
addressesIssue|JudicialDecision|LegalIssue|jurisprudence|true|Legal issue addressed by a decision.
recordsArgument|JudicialDecision|PartyArgument|jurisprudence|false|Recorded party argument, not a finding.
allegesFact|PartyArgument|AllegedFact|jurisprudence|false|Allegation is not adjudicated fact.
findsFact|JudicialDecision|JudicialFinding|jurisprudence|true|Finding attributed to the deciding body.
adoptsHolding|JudicialDecision|Holding|jurisprudence|true|Holding distinct from dicta or editorial summary.
hasDisposition|JudicialDecision|Disposition|jurisprudence|true|Operative outcome, with scope preserved.
cites|LegalEntity|LegalEntity|jurisprudence|false|Citation existence does not imply support or application.
quotes|LegalEntity|LegalEntity|jurisprudence|false|Textual quotation does not imply endorsement.
interprets|Holding|ProvisionVersion|jurisprudence|true|Interpretation of an exact provision version.
applies|JudicialDecision|ProvisionVersion|jurisprudence|true|Application of a version; unresolved versions are excluded.
distinguishes|JudicialDecision|JudicialDecision|jurisprudence|true|Reasoned treatment of another decision.
declinesToApply|JudicialDecision|LegalEntity|jurisprudence|true|Nonapplication with qualified grounds.
criticizes|Opinion|LegalEntity|jurisprudence|true|Criticism is not invalidation.
reviewsDecision|JudicialDecision|JudicialDecision|jurisprudence|true|Procedural review relationship.
affirms|JudicialDecision|JudicialDecision|jurisprudence|true|Affirmance with its scope preserved.
setsAside|JudicialDecision|JudicialDecision|jurisprudence|true|Setting aside is not legislative repeal.
remands|JudicialDecision|Proceeding|jurisprudence|true|Remand of a proceeding.
hasFactPattern|JudicialDecision|FactPattern|jurisprudence|true|Reviewed abstraction preserving material differences.
supportsInterpretation|JudicialDecision|Holding|jurisprudence|true|Support is distinct from binding effect.
conflictsOnIssue|ConflictAssessment|LegalIssue|jurisprudence|true|Qualified conflict, not automatic overruling.
comparesAuthority|ConflictAssessment|JudicialDecision|jurisprudence|true|Authorities considered in a conflict assessment.
developsInterpretation|JudicialDecision|Holding|jurisprudence|true|Change in reasoning does not itself repeal law.
hasUnresolvedReference|CitationOccurrence|UnresolvedReference|jurisprudence|false|Unknown reference must not resolve to the latest version.
bindingEffectUnder|AuthorityTreatment|ProvisionVersion|jurisprudence|true|Binding effect requires a separately evidenced legal basis.
representedBy|LegalEntity|SourceRepresentation|evidence|false|Representation distinct from canonical legal identity.
derivedFrom|Entity|Entity|evidence|false|Data provenance does not establish legal authority.
supportedBy|Assertion|EvidencePassage|evidence|false|Evidence for a specific assertion, not blanket document support.
inArtifact|EvidencePassage|SourceArtifact|evidence|false|Exact source artifact of a passage.
belongsToCollection|SourceArtifact|SourceCollection|evidence|false|Source collection membership.
reviewedBy|Assertion|LegalReview|evidence|false|Review record scoped to an assertion.
hasDerivation|Assertion|Derivation|evidence|false|Explicit inference derivation.
supersedesAssertion|Assertion|Assertion|evidence|false|Correction of system knowledge, not repeal of law.
hasRightsRecord|SourceArtifact|RightsRecord|evidence|false|Permitted use must be established separately.
aboutMatter|Entity|Matter|private_overlay|false|Private matter scope; never materialized in public graphs.
hasMatterDocument|Matter|MatterDocument|private_overlay|false|Private authorized document membership.
hasMatterFact|Matter|MatterFact|private_overlay|false|Private fact may remain alleged or disputed.
referencesAuthority|MatterAssertion|LegalEntity|private_overlay|true|Private-to-public reference with no public inverse.
supportsClaim|MatterAssertion|Claim|private_overlay|true|Support scoped to the matter and work-product version.
dependsOn|WorkProductVersion|Entity|private_overlay|false|Dependency used for stale-work-product review.
corrects|LawyerCorrection|MatterAssertion|private_overlay|false|Scoped correction must not update public authority automatically.
reviewsWorkProduct|ReviewDecision|WorkProductVersion|private_overlay|false|Review scoped to an immutable product version.
"""

DOMAINS = """
law|Hukuk|Law|
private_law|Özel hukuk|Private law|law
public_law|Kamu hukuku|Public law|law
international|Uluslararası hukuk|International law|law
procedural|Usul hukuku|Procedural law|law
civil|Medeni hukuk|Civil law|private_law
contracts|Sözleşmeler hukuku|Contract law|civil
obligations|Borçlar hukuku|Law of obligations|civil
property|Eşya hukuku|Property law|civil
family|Aile hukuku|Family law|civil
inheritance|Miras hukuku|Inheritance law|civil
persons|Kişiler hukuku|Law of persons|civil
commercial|Ticaret hukuku|Commercial law|private_law
company|Şirketler hukuku|Company law|commercial
negotiable_instruments|Kıymetli evrak hukuku|Negotiable instruments|commercial
insurance|Sigorta hukuku|Insurance law|commercial
maritime|Deniz ticareti hukuku|Maritime commercial law|commercial
employment|İş hukuku|Employment law|law
social_security|Sosyal güvenlik hukuku|Social security law|public_law
consumer|Tüketici hukuku|Consumer law|law
intellectual_property|Fikri mülkiyet hukuku|Intellectual property law|private_law
real_estate|Taşınmaz hukuku|Real estate law|law
constitutional|Anayasa hukuku|Constitutional law|public_law
administrative|İdare hukuku|Administrative law|public_law
tax|Vergi hukuku|Tax law|public_law
criminal|Ceza hukuku|Criminal law|public_law
criminal_enforcement|Ceza infaz hukuku|Criminal enforcement law|public_law
human_rights|İnsan hakları hukuku|Human rights law|law
data_protection|Kişisel verilerin korunması|Data protection law|law
competition|Rekabet hukuku|Competition law|public_law
public_procurement|Kamu ihale hukuku|Public procurement law|public_law
public_finance|Kamu mali hukuku|Public finance law|public_law
banking|Bankacılık hukuku|Banking law|law
capital_markets|Sermaye piyasası hukuku|Capital markets law|law
energy|Enerji hukuku|Energy law|law
environment|Çevre hukuku|Environmental law|law
health|Sağlık hukuku|Health law|law
immigration|Yabancılar ve göç hukuku|Immigration law|public_law
citizenship|Vatandaşlık hukuku|Citizenship law|public_law
customs_trade|Gümrük ve dış ticaret hukuku|Customs and foreign trade|law
technology|Bilişim hukuku|Information technology law|law
transport|Taşıma hukuku|Transport law|law
zoning|İmar hukuku|Planning and zoning law|administrative
civil_procedure|Medeni usul hukuku|Civil procedure|procedural
criminal_procedure|Ceza muhakemesi hukuku|Criminal procedure|procedural
administrative_procedure|İdari yargılama hukuku|Administrative judicial procedure|procedural
enforcement_bankruptcy|İcra ve iflas hukuku|Enforcement and bankruptcy|procedural
dispute_resolution|Alternatif uyuşmazlık çözümü|Alternative dispute resolution|procedural
international_private|Milletlerarası özel hukuk|Private international law|international
international_public|Devletler umumi hukuku|Public international law|international
legal_profession|Avukatlık ve meslek kuralları|Legal profession and professional rules|law
"""

DATA_PROPERTIES = {
    "reviewStatus": "string", "claimStatus": "string", "scope": "string", "graphFamily": "string",
    "module": "string", "requiresLegalReview": "boolean", "synthetic": "boolean", "canonicalId": "string",
    "validFrom": "date", "validTo": "date", "validityStatus": "string", "recordedAt": "dateTime",
    "supersededAt": "dateTime", "publishedAt": "dateTime", "decisionDate": "date", "effectiveDate": "date",
    "finalityDate": "date", "finalityStatus": "string", "fetchedAt": "dateTime", "reviewedAt": "dateTime",
    "reviewer": "string", "extractionMethod": "string", "extractorVersion": "string", "confidence": "decimal",
    "contentHash": "string", "locator": "string", "quotedText": "string", "rightsStatus": "string",
    "legalBasis": "string", "versionResolution": "string", "unresolvedReason": "string", "reviewNote": "string",
    "knownDenominator": "integer", "observedCount": "integer", "cutoffDate": "date", "matterId": "string",
    "startOffset": "integer", "endOffset": "integer", "locatorMapHash": "string",
}

# Engineering terminology only; Turkish legal terminology still needs sign-off.
TR_LABELS = dict(line.split("=", 1) for line in """
Entity=Varlık
LegalEntity=Hukuki varlık
SchemaCategory=Şema kategorisi
LegalDomain=Hukuk alanı
LegalConcept=Hukuki kavram
DefinedTerm=Tanımlanmış terim
RoleType=Rol türü
AgentType=Özne türü
EventType=Olay türü
FactPattern=Soyut olay örüntüsü
Identifier=Tanımlayıcı
TimeInterval=Zaman aralığı
Jurisdiction=Yargı yetki alanı
TerritorialArea=Coğrafi alan
Agent=Özne
NaturalPerson=Gerçek kişi
LegalPerson=Tüzel kişi
ParticipantRole=Katılımcı rolü
Event=Olay
MonetaryAmount=Parasal tutar
ReferenceTable=Sürümlü referans tablosu
ReferenceValue=Yürürlük dönemine bağlı referans değeri
InstrumentType=Hukuki düzenleme türü
LegalInstrument=Hukuki düzenleme kimliği
InstrumentVersion=Hukuki düzenleme sürümü
Provision=Hüküm kimliği
ProvisionVersion=Hüküm metni sürümü
TextSubdivision=Metin bölümü
Article=Madde
Paragraph=Fıkra
Subparagraph=Bent
PublicationEvent=Yayımlanma olayı
EnactmentEvent=Kabul olayı
AmendmentEvent=Değişiklik olayı
RepealEvent=Yürürlükten kaldırma olayı
AnnulmentEvent=İptal olayı
TransitionalRule=Geçiş hükmü
LegislativeProposal=Kanun teklifi
LegislativeProceeding=Yasama süreci
LegislativeReason=Yasama gerekçesi
Consolidation=Birleştirilmiş metin gösterimi
TreatyInstrument=Uluslararası antlaşma
HistoricalPredecessor=Tarihsel öncül
InstitutionType=Kurum türü
Institution=Kurum
OrganizationalUnit=Teşkilat birimi
Court=Mahkeme
CourtChamber=Mahkeme dairesi
JudicialCouncil=Yargı kurulu
LegislativeBody=Yasama organı
ExecutiveBody=Yürütme organı
AdministrativeAuthority=İdari makam
Regulator=Düzenleyici kurum
ProfessionalBody=Meslek kuruluşu
EnforcementOffice=İcra dairesi
DisputeResolutionBody=Uyuşmazlık çözüm mercii
InstitutionalChange=Kurumsal değişiklik olayı
CompetenceAssignment=Koşullu görev ve yetki tanımı
CompetenceRestriction=Görev ve yetki sınırlaması
JurisdictionRule=Görev ve yetki kuralı
ReviewRoute=İnceleme veya kanun yolu
NormativeRule=Koşullu hukuk kuralı
LegalPosition=Hukuki konum
Right=Hak
Obligation=Yükümlülük
Prohibition=Yasak
Permission=İzin
LegalPower=Hukuki yetki
Immunity=Bağışıklık
Liability=Sorumluluk
LegalCondition=Hukuki koşul
LegalElement=Hukuki unsur
Exception=İstisna
Consequence=Hukuki sonuç
Remedy=Hukuki giderim yolu
Sanction=Yaptırım
ContractType=Sözleşme türü
ClauseType=Sözleşme şartı türü
ContractualPosition=Sözleşmesel hukuki konum
ProcedureType=Usul türü
Procedure=Usul tanımı
ProceduralStage=Usul aşaması
ProceduralRequirement=Usuli gereklilik
ProceduralAct=Usul işlemi
DeadlineRule=Koşullu süre kuralı
DeadlineTrigger=Süreyi başlatan olay
TimeComputationRule=Süre hesaplama kuralı
ProofBurden=İspat yükü
ProofStandard=İspat ölçüsü
AdmissibilityCondition=Kabul edilebilirlik koşulu
EvidenceCategory=Delil kategorisi
AlternativeDisputeResolution=Alternatif uyuşmazlık çözüm usulü
Proceeding=Yargılama kimliği
ProceedingStage=Somut yargılama aşaması
JudicialDecision=Yargı kararı kimliği
DecisionVersion=Karar metni sürümü
DecisionType=Karar türü
Panel=Karar veren heyet
Opinion=Görüş
Dissent=Karşıoy
LegalIssue=Hukuki mesele
PartyArgument=Taraf iddiası veya savunması
AllegedFact=İleri sürülen vakıa
JudicialFinding=Mahkemenin maddi vakıa tespiti
Holding=Kararda benimsenen hukuki görüş
Disposition=Hüküm sonucu
CitationOccurrence=Metindeki atıf
UnresolvedReference=Çözümlenemeyen atıf veya sürüm
AuthorityTreatment=Kaynağın değerlendirilme biçimi
ApplicabilityAssessment=Koşullu uygulanabilirlik değerlendirmesi
ConflictAssessment=İçtihat çelişkisi değerlendirmesi
TrendHypothesis=İçtihat eğilimi varsayımı
EditorialAnnotation=Editoryal açıklama
SourceArtifact=Değişmez kaynak dosyası
SourceRepresentation=Kaynak metin gösterimi
EvidencePassage=Kesin kaynak bölümü
Assertion=Kaynağa dayalı ilişki iddiası
LegalReview=Hukukçu inceleme kaydı
Derivation=Çıkarım dayanağı
ExtractionRun=Metin çıkarma çalıştırması
GraphSnapshot=Değişmez graf anlık görüntüsü
SourceCollection=Kaynak koleksiyonu
CoverageRecord=Kapsam gözlemi
RightsRecord=Kullanım hakları kaydı
Matter=Hukuki çalışma dosyası
MatterDocument=Dosyaya ait özel belge
MatterFact=Dosyaya ait vakıa
MatterEvent=Dosyaya ait olay
MatterAssertion=Dosyaya ait ilişki iddiası
MatterParty=Dosya tarafı
WorkProduct=Özel çalışma ürünü
WorkProductVersion=Çalışma ürünü sürümü
Claim=Çalışma ürünündeki önerme
LawyerCorrection=Dosyaya özgü avukat düzeltmesi
ReviewDecision=Çalışma ürünü inceleme kararı
instanceOf=Türüne aittir
inDomain=Hukuk alanına aittir
hasRole=Katılımcı rolü vardır
roleType=Rol türüdür
hasParticipant=Katılımcısı vardır
occursIn=Yerde gerçekleşir
patternOf=Olay türünün örüntüsüdür
definedBy=Hükümle tanımlanır
conceptRelatedTo=Kavramla ilişkilidir
hasReferenceValue=Referans değeri vardır
containsProvision=Hükmü içerir
hasInstrumentVersion=Düzenleme sürümü vardır
hasProvisionVersion=Hüküm sürümü vardır
versionOf=Sürümüdür
hasSubdivision=Metin alt bölümü vardır
publishedIn=Yayımlanma olayına bağlıdır
enactedBy=Organ tarafından kabul edilmiştir
amends=Hükmü değiştirir
createsVersion=Sürümü oluşturur
repeals=Yürürlükten kaldırır
annuls=İptal eder
replaces=Hukuken yerine geçer
renumbers=Hükmü yeniden numaralandırır
splitsFrom=Hükümden ayrılmıştır
mergesFrom=Hükümden birleştirilmiştir
hasTransitionRule=Geçiş hükmüne bağlıdır
hasLegislativeReason=Yasama gerekçesi vardır
consolidates=Sürümü birleştirilmiş olarak gösterir
predecessorOf=Tarihsel öncülüdür
influencedBy=Tarihsel olarak etkilenmiştir
organizationalPartOf=Teşkilatın parçasıdır
establishedBy=Hükümle kurulmuştur
renamedFrom=Önceki adından yeniden adlandırılmıştır
successorOf=Kurumsal halefidir
abolishedBy=Olayla kaldırılmıştır
heldBy=Yetkiyi kurum kullanır
authorizedBy=Yetkisini hükümden alır
coversSubject=Konuyu kapsar
coversTerritory=Coğrafi alanı kapsar
coversProcedure=Usulü kapsar
restrictedBy=Sınırlamaya tabidir
routeFrom=İnceleme yolunun çıkış merciidir
routeTo=İnceleme yolunun varış merciidir
supervisedBy=Kurumun gözetimine tabidir
createdBy=Hükümle oluşturulmuştur
heldByRole=Rol tarafından taşınır
owedByRole=Yükümlülüğü rol taşır
requiresCondition=Koşulu gerektirir
hasElement=Hukuki unsuru vardır
subjectToException=İstisnaya tabidir
hasConsequence=Hukuki sonucu vardır
remediedBy=Giderim yoluyla korunur
expressedBy=Hükümde ifade edilir
hasClauseType=Sözleşme şartı türü içerir
hasStage=Usul aşaması vardır
requiresStep=Usuli adımı gerektirir
triggeredBy=Olayla başlar
computedBy=Kuralla hesaplanır
subjectToDeadline=Süreye tabidir
requiresProofOf=Unsurun ispatını gerektirir
usesProofStandard=İspat ölçüsünü kullanır
hasAdmissibilityCondition=Kabul edilebilirlik koşulu vardır
decidedIn=Yargılamada karara bağlanmıştır
issuedBy=Merci tarafından verilmiştir
decidedByPanel=Heyet tarafından karara bağlanmıştır
issuedAtStage=Yargılama aşamasında verilmiştir
hasDecisionVersion=Karar metni sürümü vardır
hasOpinion=Görüş içerir
addressesIssue=Hukuki meseleyi ele alır
recordsArgument=Taraf iddiasını veya savunmasını kaydeder
allegesFact=Vakıayı ileri sürer
findsFact=Maddi vakıayı tespit eder
adoptsHolding=Hukuki görüşü benimser
hasDisposition=Hüküm sonucu vardır
cites=Atıf yapar
quotes=Alıntı yapar
interprets=Hüküm sürümünü yorumlar
applies=Hüküm sürümünü uygular
distinguishes=Kararı somut olaydan ayırır
declinesToApply=Uygulamayı reddeder
criticizes=Eleştirir
reviewsDecision=Kararı inceler
affirms=Kararı onar
setsAside=Kararı kaldırır veya bozar
remands=Yargılamayı geri gönderir
hasFactPattern=Olay örüntüsü vardır
supportsInterpretation=Yorumu destekler
conflictsOnIssue=Hukuki meselede çelişki değerlendirir
comparesAuthority=Kararı karşılaştırır
developsInterpretation=Yorumu geliştirir
hasUnresolvedReference=Çözümlenemeyen atıf içerir
bindingEffectUnder=Bağlayıcılığı hükme dayanır
representedBy=Kaynak gösterimi vardır
derivedFrom=Veriden türetilmiştir
supportedBy=Kaynak bölümüyle desteklenir
inArtifact=Kaynak dosyasındadır
belongsToCollection=Koleksiyona aittir
reviewedBy=İnceleme kaydı vardır
hasDerivation=Çıkarım dayanağı vardır
supersedesAssertion=Sistem bilgisini düzeltir
hasRightsRecord=Kullanım hakları kaydı vardır
aboutMatter=Özel dosyayla ilgilidir
hasMatterDocument=Dosyaya ait belge içerir
hasMatterFact=Dosyaya ait vakıa içerir
referencesAuthority=Hukuki kaynağa gönderme yapar
supportsClaim=Önermeyi destekler
dependsOn=Veriye bağımlıdır
corrects=Dosya iddiasını düzeltir
reviewsWorkProduct=Çalışma ürünü sürümünü inceler
""".strip().splitlines())


def rows(text):
    return [line.split("|") for line in text.strip().splitlines() if line.strip()]


def literal(value):
    return json.dumps(value, ensure_ascii=False)


def build():
    (ROOT / "modules").mkdir(parents=True, exist_ok=True)
    classes, relations = [], []
    for module, (graph, definitions) in MODULES.items():
        parts = [PREFIX]
        for ident, label, parent in rows(definitions):
            classes.append({"id": NS + ident, "label": TR_LABELS[ident], "label_en": label, "module": module, "graph": graph,
                            "parent": NS + parent if parent else None, "review_status": "unreviewed"})
            parent_ttl = f" ;\n  rdfs:subClassOf la:{parent}" if parent else ""
            parts.append(f"la:{ident} a owl:Class ; rdfs:label {literal(TR_LABELS[ident])}@tr, {literal(label)}@en ;\n"
                         f"  la:module {literal(module)} ; la:graphFamily {literal(graph)} ;\n"
                         f"  la:reviewStatus \"unreviewed\"{parent_ttl} .\n")
        for ident, domain, range_, mod, review, meaning in rows(RELATIONS):
            if mod != module:
                continue
            relations.append({"id": NS + ident, "label": TR_LABELS[ident], "label_en": ident, "predicate_code": ident, "module": module, "graph": graph,
                              "domain": NS + domain, "range": NS + range_, "description": meaning,
                              "requires_legal_review": review == "true", "review_status": "unreviewed"})
            parts.append(f"la:{ident} a owl:ObjectProperty ; rdfs:label {literal(TR_LABELS[ident])}@tr, {literal(ident)}@en ;\n"
                         f"  rdfs:domain la:{domain} ; rdfs:range la:{range_} ;\n"
                         f"  rdfs:comment {literal(meaning)}@en ; la:module {literal(module)} ;\n"
                         f"  la:requiresLegalReview {review} ; la:reviewStatus \"unreviewed\" .\n")
        if module == "evidence":
            for ident, type_ in DATA_PROPERTIES.items():
                parts.append(f"la:{ident} a owl:DatatypeProperty ; rdfs:range xsd:{type_} .\n")
            for ident in ("subject", "predicate", "object", "evidence", "artifact", "snapshot", "textRepresentation"):
                parts.append(f"la:{ident} a owl:ObjectProperty .\n")
        (ROOT / "modules" / f"{module}.ttl").write_text("\n".join(parts), encoding="utf-8")
    domains, parts = [], [PREFIX, 'la:TurkeyLegalDomains a skos:ConceptScheme ; rdfs:label "Türkiye legal domains — engineering taxonomy, UNREVIEWED"@en .\n']
    for ident, tr, en, parent in rows(DOMAINS):
        domains.append({"id": NS + "domain/" + ident, "key": ident, "label": tr, "label_en": en,
                        "broader": NS + "domain/" + parent if parent else None, "review_status": "unreviewed",
                        "initial_deep_validation": ident in {"contracts", "commercial", "employment"}})
        parent_ttl = f" ; skos:broader <{NS}domain/{parent}>" if parent else ""
        parts.append(f"<{NS}domain/{ident}> a skos:Concept, la:LegalDomain ;\n"
                     f"  skos:inScheme la:TurkeyLegalDomains ; skos:prefLabel {literal(tr)}@tr, {literal(en)}@en ;\n"
                     f"  la:reviewStatus \"unreviewed\"{parent_ttl} .\n")
    (ROOT / "domains.ttl").write_text("\n".join(parts), encoding="utf-8")
    catalog = {"version": VERSION, "namespace": NS, "review_status": "unreviewed",
               "status_notice": "Engineering ontology baseline. National legal review is required. No historical corpus is bundled.",
               "historical_scope": {"from_year": 1920, "pre_1920": "Only predecessors needed for continuity or applicable law; individually evidenced."},
               "initial_deep_practices": ["contracts", "commercial", "employment"],
               "domains": domains, "classes": classes, "relations": relations,
               "tool_allowlist": ["locate_issues", "resolve_authority", "trace_norm_history", "trace_institution_history",
                                  "trace_decision_history", "expand_authorities", "get_evidence", "get_coverage"]}
    (ROOT / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"classes": len(classes), "relations": len(relations), "domains": len(domains)}))


if __name__ == "__main__":
    build()
