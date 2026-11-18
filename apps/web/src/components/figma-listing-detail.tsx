import type { ListingDetailData } from "@/components/listing-detail";

const assetPathPrefix = "/assets";
const img2033099641 = `${assetPathPrefix}/11b5b.png`;
const imgPhoto17311463752608880E76012801 = `${assetPathPrefix}/a5803.png`;
const imgBasemapImage = `${assetPathPrefix}/d6c9f.png`;
const imgA965Fc3194D0437BA9C580E7Fc45Ae991 = `${assetPathPrefix}/f0d7f.png`;
const imgIconamoonScreenFullFill = `${assetPathPrefix}/fa116.svg`;
const imgFrame159 = `${assetPathPrefix}/c9b4d.svg`;
const imgVector = `${assetPathPrefix}/6ea88.svg`;
const imgEllipse2 = `${assetPathPrefix}/56c7d.svg`;
const imgVector1 = `${assetPathPrefix}/98df3.svg`;
const imgVector2 = `${assetPathPrefix}/7b8b2.svg`;
const imgHeroiconsOutlineStatusOnline = `${assetPathPrefix}/26bc2.svg`;
const imgEllipse4 = `${assetPathPrefix}/5a07e.svg`;
const imgWeuiArrowOutlined = `${assetPathPrefix}/3ed55.svg`;
const imgMaterialSymbolsLightBedOutlineRounded = `${assetPathPrefix}/6fe6e.svg`;
const imgIconoirBalcony = `${assetPathPrefix}/c0520.svg`;
const imgGroup = `${assetPathPrefix}/c338a.svg`;
const imgWeuiArrowOutlined1 = `${assetPathPrefix}/84591.svg`;
const imgGroup1 = `${assetPathPrefix}/d12b5.svg`;
const imgCarbonUserService = `${assetPathPrefix}/75d3d.svg`;
const imgGroup2 = `${assetPathPrefix}/fbcb1.svg`;
const imgGroup3 = `${assetPathPrefix}/80308.svg`;
const imgCarbonUserService1 = `${assetPathPrefix}/1352a.svg`;
const imgGroup4 = `${assetPathPrefix}/5763e.svg`;
const imgGuidanceNoPetsAllowed = `${assetPathPrefix}/4fda4.svg`;
const imgMaterialSymbolsLightSchoolOutline = `${assetPathPrefix}/c0c43.svg`;
const imgMaterialSymbolsLightLocalPoliceOutline = `${assetPathPrefix}/c258d.svg`;
const imgMageHospitalPlus = `${assetPathPrefix}/46d3c.svg`;
const imgMaterialSymbolsLightTrainOutlineRounded = `${assetPathPrefix}/712bb.svg`;
const imgMaterialSymbolsLightLocalMallOutlineSharp = `${assetPathPrefix}/351bb.svg`;
const imgFluentMdl2Cafe = `${assetPathPrefix}/48917.svg`;
const imgVector3 = `${assetPathPrefix}/8b294.svg`;
const imgVector4 = `${assetPathPrefix}/18067.svg`;
const imgLucideHouse = `${assetPathPrefix}/14517.svg`;
const imgLucideMapPinSearch = `${assetPathPrefix}/bc8d0.svg`;
const imgLucideBookmark = `${assetPathPrefix}/c12b9.svg`;
const imgLucideUserRound = `${assetPathPrefix}/0808c.svg`;
const imgVector5 = `${assetPathPrefix}/3f197.svg`;

export function FigmaListingDetail({ listing }: { listing: ListingDetailData }) {
  const photo = listing.photos[0]?.original_url ?? img2033099641;
  const location = listing.location_label ?? (listing.point ? `${Math.abs(listing.point.latitude).toFixed(3)}° ${listing.point.latitude >= 0 ? "N" : "S"}, ${Math.abs(listing.point.longitude).toFixed(3)}° ${listing.point.longitude >= 0 ? "E" : "W"}` : "");
  const rentValue = Number(listing.rent_amount);
  const rent = `Rs. ${Number.isFinite(rentValue) ? new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(rentValue) : listing.rent_amount}/month`;
  const whatsappNumber = listing.whatsapp?.replace(/\D/g, "");
  const whatsappHref = whatsappNumber ? `https://wa.me/${whatsappNumber.startsWith("977") ? whatsappNumber : `977${whatsappNumber.replace(/^0/, "")}`}` : null;
  const postedAge = (value: string) => { const days = Math.floor(Math.max(0, Date.now() - new Date(value).getTime()) / 86400000); return !Number.isFinite(days) || days === 0 ? "Today" : days === 1 ? "1 day ago" : `${days} days ago`; };
  return (
    <div
      className="listing-handoff-root bg-[#f7f7f7] relative min-h-[4427px] w-full overflow-hidden"
      data-node-id="1:18"
      data-name="Tenant - Card Screen"
    >
      <div
        className="absolute h-[10px] left-[calc(25%+29px)] top-[28px] w-[6px]"
        data-node-id="1:25"
        data-name="mdi:letter-r"
      />
      <div
        className="absolute content-stretch flex flex-col gap-[100px] items-start left-[8px] top-[151px] w-[1230px]"
        data-node-id="1:26"
      >
        <div
          className="content-stretch flex gap-[30px] items-center relative shrink-0 w-full"
          data-node-id="1:27"
        >
          <div
            className="content-stretch flex flex-col gap-[17px] items-center relative shrink-0 w-[624.867px]"
            data-node-id="1:28"
          >
            <div
              className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0"
              data-node-id="1:29"
            >
              <div
                className="col-1 h-[418px] ml-0 mt-0 relative rounded-[30px] row-1 w-[624.867px]"
                data-node-id="1:30"
                data-name="203309964 1"
              >
                <img
                  alt=""
                  className="absolute inset-0 max-w-none object-cover pointer-events-none rounded-[30px] size-full"
                  src={photo}
                />
              </div>
              <div
                className="col-1 ml-[563.02px] mt-[31.99px] relative row-1 size-[40.52px]"
                data-node-id="1:31"
                data-name="iconamoon:screen-full-fill"
              >
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgIconamoonScreenFullFill}
                />
              </div>
              <div
                className="bg-[rgba(109,103,103,0.25)] col-1 content-stretch flex h-[41.587px] items-center justify-center ml-[490.51px] mt-[31.99px] p-[10px] relative rounded-[30px] row-1 w-[66.112px]"
                data-node-id="1:33"
              >
                <p
                  className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#fafafa] text-[14px] whitespace-nowrap"
                  data-node-id="1:34"
                >
                  See all
                </p>
              </div>
            </div>
            <div
              className="content-stretch flex items-center justify-center relative shrink-0"
              data-node-id="1:35"
            >
              <div className="h-[15px] relative shrink-0 w-[55px]" data-node-id="1:36">
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgFrame159}
                />
              </div>
            </div>
          </div>
          <div
            className="content-stretch flex flex-col gap-[45px] items-start relative shrink-0 w-[561px]"
            data-node-id="1:40"
          >
            <div
              className="content-stretch flex flex-col gap-[20px] items-start relative shrink-0 w-full"
              data-node-id="1:41"
            >
              <div
                className="content-stretch flex items-center justify-between relative shrink-0 w-full"
                data-node-id="1:42"
              >
                <div
                  className="content-stretch flex items-center mr-[-498.463px] pr-[11px] relative shrink-0 w-[1038px]"
                  data-node-id="1:43"
                >
                  <p
                    className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[#2b2b2b] text-[28px] w-[713px]"
                    data-node-id="1:44"
                    style={{ fontVariationSettings: '"wdth" 100' }}
                  >
                    {listing.title}
                  </p>
                </div>
                <div
                  className="h-[32.203px] relative shrink-0 w-[21.463px]"
                  data-node-id="1:45"
                  data-name="Vector"
                >
                  <div className="absolute inset-[-1.55%_-2.33%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector} />
                  </div>
                </div>
              </div>
              <div
                className="content-stretch flex items-center justify-center relative shrink-0"
                data-node-id="1:46"
              >
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[1.5] relative shrink-0 text-[#908e8e] text-[16px] w-[498px]"
                  data-node-id="1:47"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  {location}
                </p>
              </div>
            </div>
            <div
              className="content-stretch flex gap-[10px] h-[19px] items-center relative shrink-0 w-[295px]"
              data-node-id="1:48"
            >
              <p
                className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[1.5] relative shrink-0 text-[#2b2b2b] text-[16px] whitespace-nowrap"
                data-node-id="1:49"
                style={{ fontVariationSettings: '"wdth" 100' }}
              >
                {listing.numeric.bedrooms ?? "2"} Bed
              </p>
              <div className="relative shrink-0 size-[8px]" data-node-id="1:50">
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgEllipse2}
                />
              </div>
              <p
                className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[1.5] relative shrink-0 text-[#2b2b2b] text-[16px] whitespace-nowrap"
                data-node-id="1:51"
                style={{ fontVariationSettings: '"wdth" 100' }}
              >
                {listing.numeric.bathrooms_total ?? "3"} Bath
              </p>
              <div className="relative shrink-0 size-[8px]" data-node-id="1:52">
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgEllipse2}
                />
              </div>
              <p
                className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[1.5] relative shrink-0 text-[#2b2b2b] text-[16px] whitespace-nowrap"
                data-node-id="1:53"
                style={{ fontVariationSettings: '"wdth" 100' }}
              >
                {listing.numeric.size_value ?? "5000"} Sq.ft
              </p>
            </div>
            <div
              className="content-stretch flex items-end pr-[10px] relative shrink-0 w-full"
              data-node-id="1:54"
            >
              <div
                className="content-stretch flex items-center justify-center relative shrink-0"
                data-node-id="1:55"
              >
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[#2b2b2b] text-[28px] whitespace-nowrap"
                  data-node-id="1:56"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  {rent}
                </p>
              </div>
            </div>
            <div
              className="content-stretch flex items-start justify-center relative shrink-0 w-full"
              data-node-id="1:57"
            >
              <div
                className="content-stretch flex flex-col items-center relative shrink-0"
                data-node-id="1:58"
              >
                <div
                  className="content-stretch flex flex-col items-center justify-center relative shrink-0"
                  data-node-id="1:59"
                >
                  <div
                    className="content-stretch flex gap-[22px] items-end justify-center relative shrink-0"
                    data-node-id="1:60"
                  >
                    <div
                      className="bg-[#2275d7] content-stretch flex gap-[10px] h-[50.769px] items-center justify-center overflow-clip p-[15px] relative rounded-[20px] shrink-0 w-[154px]"
                      data-node-id="1:61"
                      data-name="hugeicons:call"
                    >
                      <div
                        className="relative shrink-0 size-[16px]"
                        data-node-id="1:62"
                        data-name="Vector"
                      >
                        <div className="absolute inset-[-7.81%_-7.81%_-7.82%_-7.82%]">
                          <img alt="" className="block max-w-none size-full" src={imgVector1} />
                        </div>
                      </div>
                      <p
                        className="[word-break:break-word] font-['Inter:Bold'] font-bold leading-[normal] not-italic relative shrink-0 text-[#fafafa] text-[16px] whitespace-nowrap"
                        data-node-id="1:63"
                      >
                        Call
                      </p>
                    {listing.whatsapp ? <a className="listing-handoff-action" href={`tel:${listing.whatsapp}`} aria-label="Call the landlord" /> : null}
            </div>
                    <div
                      className="border-2 border-[#2275d7] border-solid content-stretch flex gap-[10px] h-[50.769px] items-center justify-center overflow-clip px-[19px] py-[15px] relative rounded-[20px] shrink-0 w-[154px]"
                      data-node-id="1:64"
                      data-name="fluent:chat-12-regular"
                    >
                      <div
                        className="relative shrink-0 size-[18px]"
                        data-node-id="1:65"
                        data-name="Vector"
                      >
                        <img
                          alt=""
                          className="absolute block inset-0 max-w-none size-full"
                          src={imgVector2}
                        />
                      </div>
                      <p
                        className="[word-break:break-word] font-['Inter:Bold'] font-bold leading-[normal] not-italic relative shrink-0 text-[#2275d7] text-[16px] whitespace-nowrap"
                        data-node-id="1:66"
                      >
                        Message
                      </p>
                    {whatsappHref ? <a className="listing-handoff-action" href={whatsappHref} target="_blank" rel="noreferrer" aria-label="Message the landlord" /> : null}
            </div>
                  </div>
                </div>
              </div>
            </div>
            <div
              className="content-stretch flex gap-[35px] h-[24px] items-center justify-center relative shrink-0 w-[531px]"
              data-node-id="1:67"
            >
              <div
                className="content-stretch flex gap-[6px] items-center relative shrink-0"
                data-node-id="1:68"
              >
                <div
                  className="relative shrink-0 size-[24px]"
                  data-node-id="1:69"
                  data-name="heroicons-outline:status-online"
                >
                  <img
                    alt=""
                    className="absolute block inset-0 max-w-none size-full"
                    src={imgHeroiconsOutlineStatusOnline}
                  />
                </div>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] relative shrink-0 text-[#1f7418] text-[16px] whitespace-nowrap"
                  data-node-id="1:71"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Active
                </p>
              </div>
              <div className="relative shrink-0 size-[8px]" data-node-id="1:72">
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgEllipse4}
                />
              </div>
              <p
                className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] relative shrink-0 text-[#1f7418] text-[16px] whitespace-nowrap"
                data-node-id="1:73"
                style={{ fontVariationSettings: '"wdth" 100' }}
              >
                {postedAge(listing.created_at)}
              </p>
            </div>
          </div>
        </div>
        <div
          className="content-stretch flex items-start justify-center relative shrink-0 w-full"
          data-node-id="1:74"
        >
          <div
            className="content-stretch flex flex-col gap-[10px] items-center relative shrink-0"
            data-node-id="1:75"
          >
            <p
              className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#908e8e] text-[14px] whitespace-nowrap"
              data-node-id="1:76"
            >
              Listed by
            </p>
            <div
              className="content-stretch flex items-center relative shrink-0"
              data-node-id="1:77"
            >
              <div
                className="bg-[#fafafa] content-stretch drop-shadow-[0px_2px_7.5px_rgba(104,104,104,0.08)] flex gap-[20px] items-center pl-[10px] pr-[25px] py-[10px] relative rounded-[30px] shrink-0"
                data-node-id="1:78"
              >
                <div
                  className="relative rounded-[50px] shrink-0 size-[61px]"
                  data-node-id="1:79"
                  data-name="photo-1731146375260-8880e7601280 1"
                >
                  <img
                    alt=""
                    className="absolute inset-0 max-w-none object-cover pointer-events-none rounded-[50px] size-full"
                    src={imgPhoto17311463752608880E76012801}
                  />
                </div>
                <div
                  className="content-stretch flex gap-[66px] items-center relative shrink-0"
                  data-node-id="1:80"
                >
                  <div
                    className="content-stretch flex flex-col items-start relative shrink-0"
                    data-node-id="1:81"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[16px] text-black whitespace-nowrap"
                      data-node-id="1:82"
                    >
                      {listing.display_name ?? "Owner"}
                    </p>
                  </div>
                  <div
                    className="content-stretch flex gap-[30px] items-center justify-center relative shrink-0 w-[95px]"
                    data-node-id="1:83"
                  >
                    <div
                      className="bg-white content-stretch flex items-center justify-center relative shrink-0"
                      data-node-id="1:84"
                    >
                      <p
                        className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#09a413] text-[14px] whitespace-nowrap"
                        data-node-id="1:85"
                      >
                        Owner
                      </p>
                    </div>
                    <div
                      className="h-[36px] relative shrink-0 w-[18px]"
                      data-node-id="1:86"
                      data-name="weui:arrow-outlined"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgWeuiArrowOutlined}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div
          className="content-stretch flex flex-col gap-[20px] items-center relative shrink-0 w-[1230px]"
          data-node-id="1:88"
        >
          <div
            className="content-stretch flex flex-col gap-[50px] items-center relative shrink-0 w-full"
            data-node-id="1:89"
          >
            <div
              className="content-stretch flex flex-col items-start relative rounded-[30px] shrink-0 w-full"
              data-node-id="1:90"
            >
              <div
                className="content-stretch flex items-center justify-center relative shrink-0"
                data-node-id="1:91"
              >
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[#2b2b2b] text-[22px] whitespace-nowrap"
                  data-node-id="1:92"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Description
                </p>
              </div>
            </div>
            <div className="content-stretch flex items-start relative shrink-0" data-node-id="1:93">
              <div
                className="content-stretch flex gap-[132px] items-center relative shrink-0"
                data-node-id="1:94"
              >
                <div
                  className="content-stretch flex flex-col gap-[75px] h-[287px] items-center relative shrink-0 w-[160px]"
                  data-node-id="1:95"
                >
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:96"
                  >
                    <div
                      className="h-[21px] relative shrink-0 w-[35px]"
                      data-node-id="1:97"
                      data-name="material-symbols-light:bed-outline-rounded"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgMaterialSymbolsLightBedOutlineRounded}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[20px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:99"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:100"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:101"
                  >
                    <div
                      className="relative shrink-0 size-[37px]"
                      data-node-id="1:102"
                      data-name="iconoir:balcony"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgIconoirBalcony}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[24px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:104"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:105"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col gap-[75px] items-center relative shrink-0 w-[160px]"
                  data-node-id="1:106"
                >
                  <div
                    className="content-stretch flex flex-col gap-[14px] items-center relative shrink-0"
                    data-node-id="1:107"
                  >
                    <div
                      className="h-[39px] overflow-clip relative shrink-0 w-[37px]"
                      data-node-id="1:108"
                      data-name="solar:bath-linear"
                    >
                      <div
                        className="absolute inset-[2.33%_1.35%_2.56%_1.35%]"
                        data-node-id="1:109"
                        data-name="Group"
                      >
                        <div className="absolute inset-[0_-2.78%_-2.7%_-2.78%]">
                          <img alt="" className="block max-w-none size-full" src={imgGroup} />
                        </div>
                      </div>
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[20px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:113"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:114"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:115"
                  >
                    <div
                      className="relative shrink-0 size-[37px]"
                      data-node-id="1:116"
                      data-name="iconoir:balcony"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgIconoirBalcony}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[24px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:118"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:119"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col gap-[75px] items-center relative shrink-0 w-[160px]"
                  data-node-id="1:120"
                >
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:121"
                  >
                    <div
                      className="relative shrink-0 size-[37px]"
                      data-node-id="1:122"
                      data-name="iconoir:balcony"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgIconoirBalcony}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[24px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:124"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:125"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:126"
                  >
                    <div
                      className="h-[39px] overflow-clip relative shrink-0 w-[37px]"
                      data-node-id="1:127"
                      data-name="solar:bath-linear"
                    >
                      <div
                        className="absolute inset-[2.33%_1.35%_2.56%_1.35%]"
                        data-node-id="1:128"
                        data-name="Group"
                      >
                        <div className="absolute inset-[0_-2.78%_-2.7%_-2.78%]">
                          <img alt="" className="block max-w-none size-full" src={imgGroup} />
                        </div>
                      </div>
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[24px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:132"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:133"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col gap-[75px] items-center relative shrink-0 w-[160px]"
                  data-node-id="1:134"
                >
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:135"
                  >
                    <div
                      className="h-[21px] relative shrink-0 w-[35px]"
                      data-node-id="1:136"
                      data-name="material-symbols-light:bed-outline-rounded"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgMaterialSymbolsLightBedOutlineRounded}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[24px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:138"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:139"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:140"
                  >
                    <div
                      className="relative shrink-0 size-[37px]"
                      data-node-id="1:141"
                      data-name="iconoir:balcony"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgIconoirBalcony}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[24px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:143"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:144"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div
            className="flex h-[20px] items-center justify-center relative shrink-0 w-[40px]"
            data-node-id="1:145"
          >
            <div className="flex-none rotate-90">
              <div className="h-[40px] relative w-[20px]" data-name="weui:arrow-outlined">
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgWeuiArrowOutlined1}
                />
              </div>
            </div>
          </div>
        </div>
        <div
          className="content-stretch flex flex-col gap-[30px] items-center relative rounded-[30px] shrink-0 w-full"
          data-node-id="1:147"
        >
          <div
            className="content-stretch flex items-center relative shrink-0 w-full"
            data-node-id="1:148"
          >
            <p
              className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[#2b2b2b] text-[22px] whitespace-nowrap"
              data-node-id="1:149"
              style={{ fontVariationSettings: '"wdth" 100' }}
            >
              Ameneties
            </p>
          </div>
          <div
            className="content-stretch flex gap-[132px] items-start relative shrink-0"
            data-node-id="1:150"
          >
            <div
              className="content-stretch flex flex-col gap-[60px] items-center relative shrink-0"
              data-node-id="1:151"
            >
              <div
                className="content-stretch flex flex-col gap-[20px] items-center relative shrink-0"
                data-node-id="1:152"
              >
                <div
                  className="overflow-clip relative shrink-0 size-[37px]"
                  data-node-id="1:153"
                  data-name="healthicons:security-worker-outline"
                >
                  <div
                    className="absolute inset-[0.69%_0.74%_0.74%_0.74%]"
                    data-node-id="1:154"
                    data-name="Group"
                  >
                    <img
                      alt=""
                      className="absolute block inset-0 max-w-none size-full"
                      src={imgGroup1}
                    />
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col gap-[5px] items-center justify-center relative shrink-0"
                  data-node-id="1:159"
                >
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:160"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#2b2b2b] text-[20px] whitespace-nowrap"
                      data-node-id="1:161"
                    >
                      Security
                    </p>
                  </div>
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:162"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-normal leading-[normal] not-italic relative shrink-0 text-[#908e8e] text-[16px] text-center whitespace-nowrap"
                      data-node-id="1:163"
                    >
                      Proper Security
                    </p>
                  </div>
                </div>
              </div>
              <div
                className="content-stretch flex flex-col gap-[20px] items-center relative shrink-0"
                data-node-id="1:164"
              >
                <div
                  className="h-[37px] relative shrink-0 w-[39px]"
                  data-node-id="1:165"
                  data-name="carbon:user-service"
                >
                  <img
                    alt=""
                    className="absolute block inset-0 max-w-none size-full"
                    src={imgCarbonUserService}
                  />
                </div>
                <div
                  className="content-stretch flex flex-col gap-[5px] items-center justify-center relative shrink-0"
                  data-node-id="1:167"
                >
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:168"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#2b2b2b] text-[20px] whitespace-nowrap"
                      data-node-id="1:169"
                    >
                      Service
                    </p>
                  </div>
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0"
                    data-node-id="1:170"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-normal leading-[normal] not-italic relative shrink-0 text-[#908e8e] text-[16px] text-center w-[159px]"
                      data-node-id="1:171"
                    >{`Maintainence Service `}</p>
                  </div>
                </div>
              </div>
            </div>
            <div
              className="content-stretch flex flex-col gap-[60px] items-center relative shrink-0"
              data-node-id="1:172"
            >
              <div
                className="content-stretch flex flex-col gap-[20px] items-center relative shrink-0"
                data-node-id="1:173"
              >
                <div
                  className="overflow-clip relative shrink-0 size-[37px]"
                  data-node-id="1:174"
                  data-name="healthicons:security-worker-outline"
                >
                  <div
                    className="absolute inset-[0.69%_0.74%_0.74%_0.74%]"
                    data-node-id="1:175"
                    data-name="Group"
                  >
                    <img
                      alt=""
                      className="absolute block inset-0 max-w-none size-full"
                      src={imgGroup2}
                    />
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col gap-[5px] items-center justify-center relative shrink-0"
                  data-node-id="1:180"
                >
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:181"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#2b2b2b] text-[20px] whitespace-nowrap"
                      data-node-id="1:182"
                    >
                      Security
                    </p>
                  </div>
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:183"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-normal leading-[normal] not-italic relative shrink-0 text-[#908e8e] text-[16px] text-center whitespace-nowrap"
                      data-node-id="1:184"
                    >
                      Proper Security
                    </p>
                  </div>
                </div>
              </div>
              <div
                className="content-stretch flex flex-col gap-[20px] items-center relative shrink-0"
                data-node-id="1:185"
              >
                <div
                  className="h-[37px] relative shrink-0 w-[39px]"
                  data-node-id="1:186"
                  data-name="carbon:user-service"
                >
                  <img
                    alt=""
                    className="absolute block inset-0 max-w-none size-full"
                    src={imgCarbonUserService}
                  />
                </div>
                <div
                  className="content-stretch flex flex-col gap-[5px] items-center justify-center relative shrink-0"
                  data-node-id="1:188"
                >
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:189"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#2b2b2b] text-[20px] whitespace-nowrap"
                      data-node-id="1:190"
                    >
                      Service
                    </p>
                  </div>
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0"
                    data-node-id="1:191"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-normal leading-[normal] not-italic relative shrink-0 text-[#908e8e] text-[16px] text-center w-[159px]"
                      data-node-id="1:192"
                    >{`Maintainence Service `}</p>
                  </div>
                </div>
              </div>
            </div>
            <div
              className="content-stretch flex flex-col gap-[60px] items-center relative shrink-0"
              data-node-id="1:193"
            >
              <div
                className="content-stretch flex flex-col gap-[20px] items-center relative shrink-0"
                data-node-id="1:194"
              >
                <div
                  className="overflow-clip relative shrink-0 size-[37px]"
                  data-node-id="1:195"
                  data-name="healthicons:security-worker-outline"
                >
                  <div
                    className="absolute inset-[0.69%_0.74%_0.74%_0.74%]"
                    data-node-id="1:196"
                    data-name="Group"
                  >
                    <img
                      alt=""
                      className="absolute block inset-0 max-w-none size-full"
                      src={imgGroup1}
                    />
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col gap-[5px] items-center justify-center relative shrink-0"
                  data-node-id="1:201"
                >
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:202"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#2b2b2b] text-[20px] whitespace-nowrap"
                      data-node-id="1:203"
                    >
                      Security
                    </p>
                  </div>
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:204"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-normal leading-[normal] not-italic relative shrink-0 text-[#908e8e] text-[16px] text-center whitespace-nowrap"
                      data-node-id="1:205"
                    >
                      Proper Security
                    </p>
                  </div>
                </div>
              </div>
              <div
                className="content-stretch flex flex-col gap-[20px] items-center relative shrink-0"
                data-node-id="1:206"
              >
                <div
                  className="h-[37px] relative shrink-0 w-[39px]"
                  data-node-id="1:207"
                  data-name="carbon:user-service"
                >
                  <img
                    alt=""
                    className="absolute block inset-0 max-w-none size-full"
                    src={imgCarbonUserService}
                  />
                </div>
                <div
                  className="content-stretch flex flex-col gap-[5px] items-center justify-center relative shrink-0"
                  data-node-id="1:209"
                >
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:210"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#2b2b2b] text-[20px] whitespace-nowrap"
                      data-node-id="1:211"
                    >
                      Service
                    </p>
                  </div>
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0"
                    data-node-id="1:212"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-normal leading-[normal] not-italic relative shrink-0 text-[#908e8e] text-[16px] text-center w-[159px]"
                      data-node-id="1:213"
                    >{`Maintainence Service `}</p>
                  </div>
                </div>
              </div>
            </div>
            <div
              className="content-stretch flex flex-col gap-[60px] items-center relative shrink-0"
              data-node-id="1:214"
            >
              <div
                className="content-stretch flex flex-col gap-[20px] items-center relative shrink-0"
                data-node-id="1:215"
              >
                <div
                  className="overflow-clip relative shrink-0 size-[47px]"
                  data-node-id="1:216"
                  data-name="healthicons:security-worker-outline"
                >
                  <div
                    className="absolute inset-[0.69%_0.74%_0.74%_0.74%]"
                    data-node-id="1:217"
                    data-name="Group"
                  >
                    <img
                      alt=""
                      className="absolute block inset-0 max-w-none size-full"
                      src={imgGroup3}
                    />
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col gap-[5px] items-center justify-center relative shrink-0"
                  data-node-id="1:222"
                >
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:223"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#2b2b2b] text-[20px] whitespace-nowrap"
                      data-node-id="1:224"
                    >
                      Security
                    </p>
                  </div>
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:225"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-normal leading-[normal] not-italic relative shrink-0 text-[#908e8e] text-[16px] text-center whitespace-nowrap"
                      data-node-id="1:226"
                    >
                      Proper Security
                    </p>
                  </div>
                </div>
              </div>
              <div
                className="content-stretch flex flex-col gap-[20px] items-center relative shrink-0"
                data-node-id="1:227"
              >
                <div
                  className="h-[33px] relative shrink-0 w-[34px]"
                  data-node-id="1:228"
                  data-name="carbon:user-service"
                >
                  <img
                    alt=""
                    className="absolute block inset-0 max-w-none size-full"
                    src={imgCarbonUserService1}
                  />
                </div>
                <div
                  className="content-stretch flex flex-col gap-[5px] items-center justify-center relative shrink-0"
                  data-node-id="1:230"
                >
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0 w-full"
                    data-node-id="1:231"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#2b2b2b] text-[20px] whitespace-nowrap"
                      data-node-id="1:232"
                    >
                      Service
                    </p>
                  </div>
                  <div
                    className="content-stretch flex items-center justify-center relative shrink-0"
                    data-node-id="1:233"
                  >
                    <p
                      className="[word-break:break-word] font-['Arial'] font-normal leading-[normal] not-italic relative shrink-0 text-[#908e8e] text-[16px] text-center w-[159px]"
                      data-node-id="1:234"
                    >{`Maintainence Service `}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div
            className="flex h-[20px] items-center justify-center relative shrink-0 w-[40px]"
            data-node-id="1:235"
          >
            <div className="flex-none rotate-90">
              <div className="h-[40px] relative w-[20px]" data-name="weui:arrow-outlined">
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgWeuiArrowOutlined1}
                />
              </div>
            </div>
          </div>
        </div>
        <div
          className="content-stretch flex flex-col gap-[30px] items-start justify-center relative shrink-0 w-[1230px]"
          data-node-id="1:237"
        >
          <div
            className="content-stretch flex items-center relative shrink-0 w-full"
            data-node-id="1:238"
          >
            <p
              className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[#2b2b2b] text-[22px] whitespace-nowrap"
              data-node-id="1:239"
              style={{ fontVariationSettings: '"wdth" 100' }}
            >
              Requirements
            </p>
          </div>
          <div
            className="content-stretch flex gap-[132px] items-start justify-center relative shrink-0 w-full"
            data-node-id="1:240"
          >
            <div
              className="content-stretch flex flex-col gap-[78px] items-start relative shrink-0"
              data-node-id="1:241"
            >
              <div
                className="content-stretch flex flex-col gap-[8px] items-center relative shrink-0 w-[110px]"
                data-node-id="1:242"
              >
                <div
                  className="overflow-clip relative shrink-0 size-[51px]"
                  data-node-id="1:243"
                  data-name="fluent-emoji-flat:no-smoking"
                >
                  <div className="absolute inset-[6.25%]" data-node-id="1:244" data-name="Group">
                    <img
                      alt=""
                      className="absolute block inset-0 max-w-none size-full"
                      src={imgGroup4}
                    />
                  </div>
                </div>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[#2b2b2b] text-[20px] w-[min-content]"
                  data-node-id="1:248"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  No Smoking
                </p>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] min-w-full relative shrink-0 text-[#1f7418] text-[14px] text-center w-[min-content]"
                  data-node-id="1:249"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Match
                </p>
              </div>
              <div
                className="content-stretch flex flex-col gap-[8px] items-center relative shrink-0 w-[110px]"
                data-node-id="1:250"
              >
                <div
                  className="relative shrink-0 size-[49px]"
                  data-node-id="1:251"
                  data-name="guidance:no-pets-allowed"
                >
                  <img
                    alt=""
                    className="absolute block inset-0 max-w-none size-full"
                    src={imgGuidanceNoPetsAllowed}
                  />
                </div>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[#2b2b2b] text-[20px] w-[min-content]"
                  data-node-id="1:253"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  No Smoking
                </p>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] min-w-full relative shrink-0 text-[#1f7418] text-[14px] text-center w-[min-content]"
                  data-node-id="1:254"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Match
                </p>
              </div>
            </div>
            <div
              className="content-stretch flex flex-col gap-[78px] items-start relative shrink-0"
              data-node-id="1:255"
            >
              <div
                className="content-stretch flex flex-col gap-[8px] items-center relative shrink-0 w-[110px]"
                data-node-id="1:256"
              >
                <div
                  className="overflow-clip relative shrink-0 size-[51px]"
                  data-node-id="1:257"
                  data-name="fluent-emoji-flat:no-smoking"
                >
                  <div className="absolute inset-[6.25%]" data-node-id="1:258" data-name="Group">
                    <img
                      alt=""
                      className="absolute block inset-0 max-w-none size-full"
                      src={imgGroup4}
                    />
                  </div>
                </div>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[#2b2b2b] text-[20px] w-[min-content]"
                  data-node-id="1:262"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  No Smoking
                </p>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] min-w-full relative shrink-0 text-[#1f7418] text-[14px] text-center w-[min-content]"
                  data-node-id="1:263"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Match
                </p>
              </div>
              <div
                className="content-stretch flex flex-col gap-[8px] items-center relative shrink-0 w-[110px]"
                data-node-id="1:264"
              >
                <div
                  className="relative shrink-0 size-[49px]"
                  data-node-id="1:265"
                  data-name="guidance:no-pets-allowed"
                >
                  <img
                    alt=""
                    className="absolute block inset-0 max-w-none size-full"
                    src={imgGuidanceNoPetsAllowed}
                  />
                </div>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[#2b2b2b] text-[20px] w-[min-content]"
                  data-node-id="1:267"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  No Smoking
                </p>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] min-w-full relative shrink-0 text-[#1f7418] text-[14px] text-center w-[min-content]"
                  data-node-id="1:268"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Match
                </p>
              </div>
            </div>
            <div
              className="content-stretch flex flex-col gap-[78px] items-start relative shrink-0"
              data-node-id="1:269"
            >
              <div
                className="content-stretch flex flex-col gap-[8px] items-center relative shrink-0 w-[110px]"
                data-node-id="1:270"
              >
                <div
                  className="overflow-clip relative shrink-0 size-[51px]"
                  data-node-id="1:271"
                  data-name="fluent-emoji-flat:no-smoking"
                >
                  <div className="absolute inset-[6.25%]" data-node-id="1:272" data-name="Group">
                    <img
                      alt=""
                      className="absolute block inset-0 max-w-none size-full"
                      src={imgGroup4}
                    />
                  </div>
                </div>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[#2b2b2b] text-[20px] w-[min-content]"
                  data-node-id="1:276"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  No Smoking
                </p>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] min-w-full relative shrink-0 text-[#1f7418] text-[14px] text-center w-[min-content]"
                  data-node-id="1:277"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Match
                </p>
              </div>
              <div
                className="content-stretch flex flex-col gap-[8px] items-center relative shrink-0 w-[110px]"
                data-node-id="1:278"
              >
                <div
                  className="relative shrink-0 size-[49px]"
                  data-node-id="1:279"
                  data-name="guidance:no-pets-allowed"
                >
                  <img
                    alt=""
                    className="absolute block inset-0 max-w-none size-full"
                    src={imgGuidanceNoPetsAllowed}
                  />
                </div>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[#2b2b2b] text-[20px] w-[min-content]"
                  data-node-id="1:281"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  No Smoking
                </p>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] min-w-full relative shrink-0 text-[#1f7418] text-[14px] text-center w-[min-content]"
                  data-node-id="1:282"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Match
                </p>
              </div>
            </div>
            <div
              className="content-stretch flex flex-col gap-[78px] items-start relative shrink-0"
              data-node-id="1:283"
            >
              <div
                className="content-stretch flex flex-col gap-[8px] items-center relative shrink-0 w-[110px]"
                data-node-id="1:284"
              >
                <div
                  className="overflow-clip relative shrink-0 size-[51px]"
                  data-node-id="1:285"
                  data-name="fluent-emoji-flat:no-smoking"
                >
                  <div className="absolute inset-[6.25%]" data-node-id="1:286" data-name="Group">
                    <img
                      alt=""
                      className="absolute block inset-0 max-w-none size-full"
                      src={imgGroup4}
                    />
                  </div>
                </div>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[#2b2b2b] text-[20px] w-[min-content]"
                  data-node-id="1:290"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  No Smoking
                </p>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] min-w-full relative shrink-0 text-[#1f7418] text-[14px] text-center w-[min-content]"
                  data-node-id="1:291"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Match
                </p>
              </div>
              <div
                className="content-stretch flex flex-col gap-[8px] items-center relative shrink-0 w-[110px]"
                data-node-id="1:292"
              >
                <div
                  className="relative shrink-0 size-[49px]"
                  data-node-id="1:293"
                  data-name="guidance:no-pets-allowed"
                >
                  <img
                    alt=""
                    className="absolute block inset-0 max-w-none size-full"
                    src={imgGuidanceNoPetsAllowed}
                  />
                </div>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[#2b2b2b] text-[20px] w-[min-content]"
                  data-node-id="1:295"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  No Smoking
                </p>
                <p
                  className="[word-break:break-word] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] min-w-full relative shrink-0 text-[#1f7418] text-[14px] text-center w-[min-content]"
                  data-node-id="1:296"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Match
                </p>
              </div>
            </div>
          </div>
          <div
            className="flex h-[20px] items-center justify-center relative shrink-0 w-[40px]"
            data-node-id="1:297"
          >
            <div className="flex-none rotate-90">
              <div className="h-[40px] relative w-[20px]" data-name="weui:arrow-outlined">
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgWeuiArrowOutlined1}
                />
              </div>
            </div>
          </div>
        </div>
        <div
          className="content-stretch flex flex-col gap-[20px] items-start justify-center relative shrink-0 w-full"
          data-node-id="1:299"
        >
          <div
            className="content-stretch flex items-center justify-center relative shrink-0"
            data-node-id="1:300"
          >
            <p
              className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[22px] text-black whitespace-nowrap"
              data-node-id="1:301"
              style={{ fontVariationSettings: '"wdth" 100' }}
            >
              Location
            </p>
          </div>
          <div
            className="content-stretch flex flex-col items-center justify-center relative shrink-0 w-full"
            data-node-id="1:302"
          >
            <div
              className="h-[300px] relative rounded-[30px] shadow-[0px_2px_15px_-2px_rgba(104,104,104,0.08)] shrink-0 w-[400px]"
              data-node-id="1:303"
              data-name="Basemap image"
            >
              <img
                alt=""
                className="absolute inset-0 max-w-none object-contain pointer-events-none rounded-[30px] size-full"
                src={imgBasemapImage}
              />
            </div>
          </div>
        </div>
        <div
          className="content-stretch flex flex-col gap-[20px] items-center justify-center relative shrink-0 w-full"
          data-node-id="1:304"
        >
          <div
            className="content-stretch flex flex-col gap-[30px] items-start relative shrink-0 w-full"
            data-node-id="1:305"
          >
            <div
              className="content-stretch flex flex-col items-start relative rounded-[30px] shrink-0 w-full"
              data-node-id="1:306"
            >
              <div
                className="[word-break:break-word] content-stretch flex gap-[10px] items-center justify-center relative shrink-0 whitespace-nowrap"
                data-node-id="1:307"
              >
                <p
                  className="font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[#2b2b2b] text-[22px]"
                  data-node-id="1:308"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  Neighborhood
                </p>
                <p
                  className="font-['IBM_Plex_Sans:Regular'] font-normal leading-[1.5] relative shrink-0 text-[#908e8e] text-[16px]"
                  data-node-id="1:309"
                  style={{ fontVariationSettings: '"wdth" 100' }}
                >
                  within 300 meters
                </p>
              </div>
            </div>
            <div
              className="content-stretch flex items-start justify-center relative shrink-0 w-full"
              data-node-id="1:310"
            >
              <div
                className="content-stretch flex gap-[132px] items-center relative shrink-0"
                data-node-id="1:311"
              >
                <div
                  className="content-stretch flex flex-col gap-[75px] h-[287px] items-center relative shrink-0 w-[160px]"
                  data-node-id="1:312"
                >
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:313"
                  >
                    <div
                      className="relative shrink-0 size-[37px]"
                      data-node-id="1:314"
                      data-name="material-symbols-light:school-outline"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgMaterialSymbolsLightSchoolOutline}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[20px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:316"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:317"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:318"
                  >
                    <div
                      className="relative shrink-0 size-[37px]"
                      data-node-id="1:319"
                      data-name="material-symbols-light:local-police-outline"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgMaterialSymbolsLightLocalPoliceOutline}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[20px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:321"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:322"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col gap-[75px] h-[287px] items-center relative shrink-0 w-[160px]"
                  data-node-id="1:323"
                >
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:324"
                  >
                    <div
                      className="relative shrink-0 size-[28px]"
                      data-node-id="1:325"
                      data-name="mage:hospital-plus"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgMageHospitalPlus}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[20px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:327"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:328"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:329"
                  >
                    <div
                      className="relative shrink-0 size-[37px]"
                      data-node-id="1:330"
                      data-name="material-symbols-light:train-outline-rounded"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgMaterialSymbolsLightTrainOutlineRounded}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[20px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:332"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:333"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col h-[287px] items-center relative shrink-0 w-[160px]"
                  data-node-id="1:334"
                >
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:335"
                  >
                    <div
                      className="relative shrink-0 size-[37px]"
                      data-node-id="1:336"
                      data-name="material-symbols-light:local-mall-outline-sharp"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgMaterialSymbolsLightLocalMallOutlineSharp}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[20px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:338"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:339"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                </div>
                <div
                  className="content-stretch flex flex-col h-[287px] items-center relative shrink-0 w-[160px]"
                  data-node-id="1:340"
                >
                  <div
                    className="content-stretch flex flex-col gap-[7px] items-center relative shrink-0"
                    data-node-id="1:341"
                  >
                    <div
                      className="relative shrink-0 size-[37px]"
                      data-node-id="1:342"
                      data-name="fluent-mdl2:cafe"
                    >
                      <img
                        alt=""
                        className="absolute block inset-0 max-w-none size-full"
                        src={imgFluentMdl2Cafe}
                      />
                    </div>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] min-w-full relative shrink-0 text-[20px] text-[rgba(153,153,153,0.6)] text-center w-[min-content]"
                      data-node-id="1:344"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      3
                    </p>
                    <p
                      className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[18px] text-[rgba(153,153,153,0.6)] text-center whitespace-nowrap"
                      data-node-id="1:345"
                      style={{ fontVariationSettings: '"wdth" 100' }}
                    >
                      Bathrooms
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div
            className="flex h-[20px] items-center justify-center relative shrink-0 w-[40px]"
            data-node-id="1:346"
          >
            <div className="flex-none rotate-90">
              <div className="h-[40px] relative w-[20px]" data-name="weui:arrow-outlined">
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgWeuiArrowOutlined1}
                />
              </div>
            </div>
          </div>
        </div>
        <div
          className="content-stretch flex flex-col gap-[40px] items-center justify-center relative shrink-0 w-full"
          data-node-id="1:348"
        >
          <div
            className="content-stretch flex flex-col gap-[20px] items-start relative shrink-0 w-full"
            data-node-id="1:349"
          >
            <div
              className="content-stretch flex items-center justify-center relative shrink-0"
              data-node-id="1:350"
            >
              <p
                className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[#2b2b2b] text-[22px] whitespace-nowrap"
                data-node-id="1:351"
                style={{ fontVariationSettings: '"wdth" 100' }}
              >
                Looks Good?
              </p>
            </div>
            <div
              className="content-stretch flex items-center justify-center relative shrink-0 w-full"
              data-node-id="1:352"
            >
              <p
                className="[word-break:break-word] flex-[1_0_0] font-['IBM_Plex_Sans:Regular'] font-normal leading-[normal] min-w-px relative text-[#2b2b2b] text-[16px]"
                data-node-id="1:353"
                style={{ fontVariationSettings: '"wdth" 100' }}
              >
                If you’re interested in this property, please contact the owner for more details, to
                schedule a visit, or to discuss lease arrangements.
              </p>
            </div>
          </div>
          <div
            className="content-stretch flex gap-[22px] items-end justify-center relative shrink-0 w-[389px]"
            data-node-id="1:354"
          >
            <div
              className="bg-[#2275d7] content-stretch flex flex-[1_0_0] gap-[10px] h-[60px] items-center justify-center min-w-px overflow-clip p-[15px] relative rounded-[30px]"
              data-node-id="1:355"
              data-name="hugeicons:call"
            >
              <div
                className="relative shrink-0 size-[22px]"
                data-node-id="1:356"
                data-name="Vector"
              >
                <div className="absolute inset-[-5.68%_-5.68%_-5.69%_-5.69%]">
                  <img alt="" className="block max-w-none size-full" src={imgVector3} />
                </div>
              </div>
              <p
                className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[#fafafa] text-[18px] whitespace-nowrap"
                data-node-id="1:357"
                style={{ fontVariationSettings: '"wdth" 100' }}
              >
                Call
              </p>
            {listing.whatsapp ? <a className="listing-handoff-action" href={`tel:${listing.whatsapp}`} aria-label="Call the landlord" /> : null}
            </div>
            <div
              className="border border-[#2275d7] border-solid content-stretch flex flex-[1_0_0] gap-[10px] h-[60px] items-center justify-center min-w-px overflow-clip px-[19px] py-[15px] relative rounded-[30px]"
              data-node-id="1:358"
              data-name="fluent:chat-12-regular"
            >
              <div
                className="relative shrink-0 size-[24px]"
                data-node-id="1:359"
                data-name="Vector"
              >
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgVector4}
                />
              </div>
              <p
                className="[word-break:break-word] font-['IBM_Plex_Sans:Medium'] font-medium leading-[normal] relative shrink-0 text-[#2275d7] text-[18px] whitespace-nowrap"
                data-node-id="1:360"
                style={{ fontVariationSettings: '"wdth" 100' }}
              >
                Message
              </p>
            {whatsappHref ? <a className="listing-handoff-action" href={whatsappHref} target="_blank" rel="noreferrer" aria-label="Message the landlord" /> : null}
            </div>
          </div>
        </div>
      </div>
      <div className="absolute contents left-[8px] top-[153px]" data-node-id="1:361">
        <div className="absolute contents left-[8px] top-[153px]" data-node-id="1:362">
          <div
            className="absolute h-[418px] left-[8px] rounded-[30px] top-[153px] w-[624.867px]"
            data-node-id="1:363"
            data-name="203309964 1"
          >
            <img
              alt=""
              className="absolute inset-0 max-w-none object-cover pointer-events-none rounded-[30px] size-full"
              src={photo}
            />
          </div>
          <div
            className="absolute left-[571.02px] size-[40.52px] top-[184.99px]"
            data-node-id="1:364"
            data-name="iconamoon:screen-full-fill"
          >
            <img
              alt=""
              className="absolute block inset-0 max-w-none size-full"
              src={imgIconamoonScreenFullFill}
            />
          </div>
          <div
            className="absolute bg-[rgba(109,103,103,0.25)] content-stretch flex h-[41.587px] items-center justify-center left-[498.51px] p-[10px] rounded-[30px] top-[184.99px] w-[66.112px]"
            data-node-id="1:366"
          >
            <p
              className="[word-break:break-word] font-['Arial'] font-semibold leading-[normal] not-italic relative shrink-0 text-[#fafafa] text-[14px] whitespace-nowrap"
              data-node-id="1:367"
            >
              See all
            </p>
          </div>
        </div>
        <div
          className="-translate-x-1/2 absolute content-stretch flex items-center justify-center left-[calc(29.17%-4.5px)] top-[588px]"
          data-node-id="1:368"
        >
          <div className="h-[15px] relative shrink-0 w-[55px]" data-node-id="1:369">
            <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame159} />
          </div>
        </div>
      </div>

    </div>
  );
}
