"""Prompt templates for semantic audit review tasks."""

from __future__ import annotations


ATTACHMENT_REVIEW_PROMPT = (
    "你是运维工单附件复核员。请判断附件是否真的是报告、证书、曲线图或现场照片，"
    "并核对附件内容是否足以支持工单结论。输出结论、证据摘要和置信度。"
)

REMARK_REVIEW_PROMPT = (
    "你是运维工单语义复核员。请判断备注是否覆盖原因、措施、结果，"
    "并说明是否足以支持工单闭环结论。输出结论、证据摘要和置信度。"
)

REMARK_SEMANTIC_JSON_PROMPT = (
    "请判断下列运维工单备注是否完整说明原因、措施、结果。"
    "如果上下文的 semantic_focus 包含 RF_TW_REMARK_LOW_VALUE，表示双周切割头清洗未识别到清洗照片；"
    "此时不要套用故障闭环三要素，也不要因为备注为空或低信息词直接判问题，"
    "只判断备注是否合理说明了未提供清洗照片或证据不足的原因。"
    "problem_description 必须具体描述备注存在或不存在的问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"is_complete\":bool,\"has_cause\":bool,\"has_action\":bool,\"has_result\":bool,"
    "\"problem_description\":string,\"confidence\":number}"
)

REMARK_BATCH_SEMANTIC_JSON_PROMPT = (
    "请逐项判断运维工单备注是否完整说明当前异常项的原因、措施、结果。"
    "仅对故障、异常、报警、待定、处置闭环类场景使用该标准；不要把计划任务主表描述充分性混入本任务。"
    "如果 semantic_focus 或证据中包含 RF_RANGE_OUT_OF_SPEC，表示表单检查值超出品牌正常范围，"
    "应重点读取备注、异常时处理记录、处理记录或处置说明，判断该异常检查值是否有基本合理的业务说明。"
    "该规则的语义复核采用宽松口径：只要备注非空，且内容与当前检查、异常处理、设备状态、复测、参数或现场情况大致相关，"
    "即使备注较简略、没有完整覆盖原因/措施/结果，也应视为备注有效，不要仅因缺少三要素而判为问题。"
    "例如‘已处理’、‘正常’、‘复测正常’、‘已调整参数’、‘设备运行正常’等简短但不明显离谱的说明，原则上判为有效备注。"
    "只有在备注为空、仅为占位符（如‘/’）、明显与当前异常无关，或与表单/处理记录明显矛盾时，才判为备注无效。"
    "必须优先读取当前异常项 issue.remark_candidates 中对应字段的CHECKROW或字段级说明。"
    "如果字段级说明明确写明表格范围有误、范围配置有误、系统表格范围错误、厂家备案参数、厂家备案范围、"
    "厂家实际参数或设备适用范围等，表示超范围来自通用范围配置与现场设备范围不一致，"
    "可视为该异常检查值已有合理业务解释，不要再按缺少原因、措施、结果判为问题。"
    "如果 semantic_focus 或证据中包含 RF_PM_TEMP_ERROR_OUT_OF_RANGE，表示颗粒物温度误差超出±2℃，"
    "应重点读取 evidence_summary.sample_issues.evidence 中的 calibration_situation 或对应校准情况字段。"
    "如果校准情况能合理说明仪器无校准功能、不适用、仅作参考或其他业务原因，不要仅因温度误差数值超限直接判问题；"
    "如果校准情况为空、低信息，或无法解释温度误差超限原因，才判为不完整。"
    "如果 semantic_focus 或证据中包含 RF_TW_REMARK_LOW_VALUE，表示双周切割头清洗未识别到清洗照片；"
    "此时不要套用故障闭环的原因、措施、结果三要素，也不要因为备注为空、/、正常、清洗等固定低信息词直接判问题。"
    "应只判断备注或上下文是否合理说明了未提供清洗照片、照片缺失、附件无法上传或其他证据不足的业务原因；"
    "如果没有合理说明，应判为不完整；如果说明合理，应判为完整。"
    "每个输入项必须独立判断，不得用同一工单其他RF表或其他字段的备注替代当前异常项说明。"
    "problem_description 必须具体描述当前review_item_id对应备注的问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"review_item_id\":string,\"working_order_code\":string,\"is_complete\":bool,\"has_cause\":bool,"
    "\"has_action\":bool,\"has_result\":bool,\"problem_description\":string,\"confidence\":number}]}"
)

ORDER_DESCRIPTION_SEMANTIC_JSON_PROMPT = (
    "请判断运维工单主表标题和内容是否足以说明本次工单的作业对象、作业类型或任务目的。"
    "不要套用故障闭环的原因、措施、结果三要素；周检、巡检、计划任务可由RF表、工单类型/周期、流程记录补充上下文。"
    "如果只有'计划任务单'且无任何RF表、作业类型、设备/站点/任务上下文，应判为不充分；"
    "如果虽然主表内容泛化，但工单类型/周期和RF表已经清楚表明是例行检查任务，可判为充分或不作为最终问题。"
    "problem_description 必须说明主表描述是否存在具体问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"is_sufficient\":bool,\"has_task_object\":bool,\"has_task_type\":bool,"
    "\"reason\":string,\"problem_description\":string,\"confidence\":number}"
)

ATTACHMENT_QUALITY_JSON_PROMPT = (
    "请根据识别文本判断附件是否完整。"
    "证书重点检查是否只是封面或首页，报告重点检查目录是否更新。"
    "problem_description 必须具体描述附件内容问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"is_complete\":bool,\"issues\":[string],\"problem_description\":string,\"confidence\":number}"
)

PHOTO_WATERMARK_JSON_PROMPT = (
    "请判断照片OCR文本中是否包含水印及日期。仅输出JSON，不要输出解释。格式为："
    "{\"has_watermark\":bool,\"has_date\":bool,\"date_text\":string,\"problem_description\":string,\"confidence\":number}"
)

VALUE_CONSISTENCY_JSON_PROMPT = (
    "请判断附件中的读数与表单值是否一致。仅输出JSON，不要输出解释。格式为："
    "{\"is_consistent\":bool,\"attachment_value\":string,\"form_value\":string,\"difference\":number,"
    "\"problem_description\":string,\"confidence\":number}"
)

FILENAME_SEMANTIC_JSON_PROMPT = (
    "请仅根据附件文件名语义，判断这些文件名是否覆盖指定的运维证据类型。"
    "不要推断图片内容，不要做OCR，不要因为扩展名是图片就认为覆盖具体证据类型。"
    "可根据中文业务含义、同义表达、缩写和上下文归类。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"covered_types\":{string:[string]},\"missing_types\":[string],"
    "\"uncertain_types\":[string],\"evidence\":[{\"type\":string,\"filenames\":[string],\"reason\":string}],"
    "\"confidence\":number}"
)

FILENAME_BATCH_SEMANTIC_JSON_PROMPT = (
    "请批量根据附件文件名语义，判断每个工单的附件是否覆盖指定的站点设备维护现场照片证据类型。"
    "每个工单会提供required_types和type_definitions，请按type_definitions理解英文类型编码。"
    "每个工单还可能提供rf_remarks，请同时判断备注是否明确说明无设备、不适用、流动监测车、停运或其他合理豁免场景。"
    "如果备注构成合理豁免，即使附件文件名未覆盖全部类型，也应返回is_exempt=true并说明exemption_reason。"
    "不要推断图片内容，不要做OCR，不要因为扩展名是图片就认为覆盖具体证据类型。"
    "可根据中文业务含义、同义表达、缩写和上下文归类。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"working_order_code\":string,\"is_exempt\":bool,\"exemption_reason\":string,"
    "\"covered_types\":{string:[string]},"
    "\"missing_types\":[string],\"uncertain_types\":[string],"
    "\"evidence\":[{\"type\":string,\"filenames\":[string],\"reason\":string}],\"confidence\":number}]}"
)

NO_DEVICE_EXPLANATION_JSON_PROMPT = (
    "请判断设备型号字段为空、/、无等占位值时，运行情况文本是否合理解释了型号字段为何缺失或占位。"
    "解释可以包括无对应设备、未配置、合同不包含、不适用、停用、拆除、故障、历史遗留、无法识别型号等实际原因。"
    "在 RF_W_OTHERDEVICECHECK 中，运行情况只写'无'可视为无对应设备；"
    "如果文本只写'/'、'正常'等低信息内容，或只描述状态但无法解释型号占位原因，应判为说明不足。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"is_explained\":bool,\"reason\":string,\"problem_description\":string,\"confidence\":number}"
)

NO_DEVICE_BATCH_JSON_PROMPT = (
    "请批量判断 RF_W_OTHERDEVICECHECK 中设备型号为占位值时，运行情况是否合理解释了型号字段为何缺失或占位。"
    "解释可以包括无对应设备、未配置、合同不包含、不适用、停用、拆除、故障、历史遗留、无法识别型号等实际原因。"
    "同一类问题使用同一标准：只判断运行情况能否支撑型号占位，不要把规则限定为是否说明无设备。"
    "当前业务口径认可运行情况只写'无'已经足够表示无对应设备；"
    "如果文本只写'/'、'正常'等低信息内容，或只描述运行状态但无法解释型号占位原因，应判为说明不足。"
    "problem_description 必须具体说明设备类型、型号占位值、运行情况文本之间的逻辑矛盾或说明不足，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"item_id\":string,\"is_explained\":bool,\"reason\":string,"
    "\"problem_description\":string,\"confidence\":number}]}"
)

PM_TAPE_USAGE_BATCH_JSON_PROMPT = (
    "请批量判断颗粒物周检 RF_W_PMCHECK 中耗材使用/处置字段填写是否规范。"
    "每个item会给出 pollutant_type、device_model、instrument_type、field、field_label 和 field_value。"
    "底层逻辑：根据 device_model 判断仪器耗材类型，并审核对应字段是否能让用户核查本次周检后的耗材状态。"
    "当 DEVICEMODEL/device_model 包含 1405 时，通常为 TEOM/振荡天平类设备，应审核 TEOMMEMBRANEDISPOSAL；"
    "其他颗粒物仪器通常使用纸带，应审核 TAPEUSAGEDISPOSAL。"
    "核查目标不是匹配固定词，而是判断 field_value 是否说明了耗材剩余量、负载、已更换、已处置或其他状态，"
    "使审核人能判断耗材能否支撑到下次维护或是否已经完成必要处置。"
    "对于 paper_tape，只要语义上能判断纸带足够使用到下次维护、剩余时间/比例/数量足量，或已更换纸带，应判为规范。"
    "对于 teom_filter，应判断TEOM滤膜负载及处置情况是否充分；如果负载达到或超过80%，且没有说明已更换或已处置，应判为不规范。"
    "如果为空、/、仅写正常/无/已检查等低信息内容，或无法判断对应耗材状态，应判为不规范。"
    "不要把判断限定为固定关键词，应按中文语义、上下文和业务目标判断。"
    "判为不规范时，problem_description 必须引用具体 field_label 和 field_value，说明为什么当前填写无法核查耗材剩余量、负载或处置状态；"
    "判为规范时，problem_description 应简要说明该内容如何支撑耗材状态判断。不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"item_id\":string,\"is_valid\":bool,\"reason\":string,\"problem_description\":string}]}"
)

ORDER_DESCRIPTION_BATCH_JSON_PROMPT = (
    "请批量判断运维工单主表标题和内容是否足以说明本次工单的作业对象、作业类型或任务目的。"
    "不要套用故障闭环的原因、措施、结果三要素；周检、巡检、计划任务可由RF表、工单类型/周期、流程记录补充上下文。"
    "如果只有'计划任务单'且无任何RF表、作业类型、设备/站点/任务上下文，应判为不充分；"
    "如果虽然主表内容泛化，但工单类型/周期和RF表已经清楚表明是例行检查任务，可判为充分或不作为最终问题。"
    "problem_description 必须说明主表描述是否存在具体问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"working_order_code\":string,\"is_sufficient\":bool,\"has_task_object\":bool,"
    "\"has_task_type\":bool,\"reason\":string,\"problem_description\":string,\"confidence\":number}]}"
)
