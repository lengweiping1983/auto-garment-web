# Image Prompt Safety Research

本文件记录了为当前项目整理的 50 条公开资料来源，并按类别归档。目标不是构造“官方完整敏感词表”，而是为本地敏感词/违禁词配置文件提供公开可追溯的依据。

## 归类结论

- 官方平台通常公开“内容限制类别”，几乎不会公开完整敏感词词表。
- 真正触发拦截的往往是“词 + 语境 + 平台策略”共同作用，而不是单个词静态命中。
- 对当前项目最实用的落地方向是：
  - 先按官方公开类别做大类过滤
  - 再结合服装印花业务做中性化改写
  - 最后持续回灌本项目的失败样本

## A. 官方政策与平台文档

1. OpenAI Help Center - How we identify problematic content on our services for individuals  
   https://help.openai.com/en/articles/8940831
2. OpenAI Usage Policies  
   https://platform.openai.com/docs/usage-policies/safety-requirements
3. OpenAI - Creating content on Sora in line with our policies  
   https://openai.com/policies/creating-images-and-videos-in-line-with-our-policies/
4. OpenAI - Combating online child sexual exploitation & abuse  
   https://openai.com/index/combating-online-child-sexual-exploitation-abuse/
5. OpenAI - UK Online Safety Act  
   https://openai.com/policies/uk-online-safety-act/
6. OpenAI - Australian Online Safety Act  
   https://openai.com/policies/au-online-safety-act/
7. OpenAI - Addendum to GPT-4o System Card: Native image generation  
   https://cdn.openai.com/11998be9-5319-4302-bfbf-1167e093f1fb/Native_Image_Generation_System_Card.pdf
8. OpenAI - Sora 2 System Card  
   https://cdn.openai.com/pdf/50d5973c-c4ff-4c2d-986f-c72b5d0ff069/sora_2_system_card.pdf
9. Google Cloud - Responsible AI and usage guidelines for Imagen  
   https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/responsible-ai-imagen
10. Google Cloud - Generative AI Prohibited Use Policy  
   https://policies.google.com/terms/generative-ai/use-policy
11. Stability AI - Acceptable Use Policy  
   https://stability.ai/use-policy
12. Midjourney - Community Guidelines  
   https://docs.midjourney.com/hc/en-us/articles/32013696484109-Community-Guidelines
13. Leonardo AI - Guide to Handling Not Safe for Work Image Generation (NSFW)  
   https://docs.leonardo.ai/docs/guide-to-handling-not-safe-for-work-image-generation-nsfw
14. Adobe Firefly - Known limitations in Firefly  
   https://helpx.adobe.com/firefly/troubleshoot/known-limitations-in-firefly.html
15. Adobe Firefly - Writing effective text prompts  
   https://helpx.adobe.com/firefly/web/generate-images-with-text-to-image/generate-images-using-text-prompts/writing-effective-text-prompts.html
16. Adobe Firefly - Enhance prompts to generate images  
   https://helpx.adobe.com/si/firefly/generate-images-with-text-to-image/generate-images-using-text-prompts/enhance-prompts-to-generate-images.html
17. Blaze - Image Generation Guidelines & Restrictions  
   https://help.blaze.ai/en/articles/14433618-image-generation-guidelines-restrictions
18. Fotor Help Center - Why is the AI generated image not approved?  
   https://support.fotor.com/hc/en-us/articles/17764598361369-Why-is-the-AI-generated-image-not-approved-What-are-the-offensive-words-Does-it-consume-credit
19. 10b.ai - Content Moderation Policy  
   https://10b.ai/content-moderation-policy
20. ImaginingAI - Content Policy  
   https://imaginingai.net/content-policy/
21. ZMO IMGCreator - Content Policy  
   https://www.zmo.ai/imgcreator/helper/content-policy
22. Z-Image - 内容审核政策  
   https://z-image.ai/zh/content-moderation-policy
23. Creator Alliance Group - Generative AI Usage Responsible Use Policy  
   https://www.creatoralliancegroup.com/generative-ai-usage-responsible-use-policy
24. Creator Alliance Group - User Safety / Content Moderation Policy  
   https://www.creatoralliancegroup.com/user-safety-content-moderation-policy
25. AI Photo Generator - Community Guidelines  
   https://www.aiphotogenerator.com/community-guidelines/

## B. 学术与研究资料

26. PromptGuard: Soft Prompt-Guided Unsafe Content Moderation for Text-to-Image Models  
   https://arxiv.org/abs/2501.03544
27. SneakyPrompt: Jailbreaking Text-to-image Generative Models  
   https://arxiv.org/abs/2305.12082
28. SafeGen: Mitigating Sexually Explicit Content Generation in Text-to-Image Models  
   https://arxiv.org/abs/2404.06666
29. PurifyGen: A Risk-Discrimination and Semantic-Purification Model for Safe Text-to-Image Generation  
   https://arxiv.org/abs/2512.23546
30. Recent progress of the security research for multimodal large models  
   https://www.cjig.cn/rc-pub/front/front-article/download/99641073/lowqualitypdf/Recent%20progress%20of%20the%20security%20research%20for%20multimodal%20large%20models.pdf
31. AIGC视觉内容生成与溯源研究进展  
   https://cjig.cn/rc-pub/front/front-article/download/61781470/lowqualitypdf/AIGC%E8%A7%86%E8%A7%89%E5%86%85%E5%AE%B9%E7%94%9F%E6%88%90%E4%B8%8E%E6%BA%AF%E6%BA%90%E7%A0%94%E7%A9%B6%E8%BF%9B%E5%B1%95.pdf

## C. 法规与合规背景

32. Interim Measures for the Management of Generative AI Services  
   https://en.wikipedia.org/wiki/Interim_Measures_for_the_Management_of_Generative_AI_Services
33. OpenAI DSA Transparency Report  
   https://cdn.openai.com/trust-and-transparency/dsa-2024-qualitative.pdf
34. OpenAI - Keeping Users Safe in the Age of AI  
   https://cdn.openai.com/global-affairs/keeping-users-safe-in-the-age-of-ai-oct25.pdf
35. Baker McKenzie - Germany authority banned GenAI text-to-picture tool  
   https://www.bakermckenzie.com/en/insight/publications/2026/03/germany-authority-banned-genai-text-to-picture-tool

## D. 新闻与行业观察

36. CNBC - Microsoft blocks terms that cause its AI to create violent images  
   https://www.cnbc.com/2024/03/08/microsoft-blocking-terms-that-cause-its-ai-to-create-violent-images.html
37. AP - Microsoft engineer sounds alarm on AI image-generator  
   https://apnews.com/article/b494180daaeb60fecfcfaead6cb00e13
38. AP - Midjourney blocks images of Biden and Trump  
   https://apnews.com/article/bc6c254ddb20e36c5e750b4570889ce1

## E. 社区误判案例与用户报告

39. Reddit - blocked or denied image generation after previously accepted prompts  
   https://www.reddit.com/r/OpenAI/comments/1lwqnmm
40. Reddit - chatgpt censors prompts saying against policy  
   https://www.reddit.com/r/ChatGPT/comments/1kh50ve
41. Reddit - Bing prompt blocking complaints  
   https://www.reddit.com/r/bing/comments/171z3sb
42. Reddit - False unsafe image content detected  
   https://www.reddit.com/r/aiArt/comments/1ak28n1
43. Reddit - Bing Image Creator blocking unexpected words  
   https://www.reddit.com/r/bing/comments/18houx1
44. Reddit - Image Creator flagging all prompts as unsafe  
   https://www.reddit.com/r/bing/comments/18ds1ye
45. Reddit - Leonardo failed generation did not meet content safety guidelines  
   https://www.reddit.com/r/leonardoai/comments/1r3htqd/everything_using_a_starting_image_is_a_failed/
46. Reddit - content policy roulette in image generation  
   https://www.reddit.com/r/OpenAI/comments/1jqdn2b
47. Reddit - Midjourney image denied for acceptable images  
   https://www.reddit.com/r/midjourney/comments/1g8je0e
48. Reddit - Replika image generator banning more words  
   https://www.reddit.com/r/replika/comments/174u80k
49. Reddit - ChatGPT image generation content policy complaints  
   https://www.reddit.com/r/ChatGPT/comments/1jn4irh

## F. 供应商补充资料

50. Leonardo - prompt appears contain inappropriate content  
   https://app.leonardo.ai/generation/image/prompt-appears-contain-inappropriate-content-25acd1b6-97db-4186-aead-416bbad5f02e

