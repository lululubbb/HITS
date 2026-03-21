package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_6_3Test {

    private CSVRecord csvRecord;
    private Map<String, Integer> mapping;
    private String[] values;

    @BeforeEach
    void setUp() {
        values = new String[]{"val0", "val1", "val2"};
        mapping = new HashMap<>();
        mapping.put("key0", 0);
        mapping.put("key1", 1);
        mapping.put("key2", 2);
        // Create CSVRecord instance using constructor
        csvRecord = new CSVRecord(values, mapping, null, 1L);
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameMappedAndIndexLessThanValuesLength() {
        // key1 mapped to index 1, which is < values.length (3)
        assertTrue(csvRecord.isSet("key1"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameMappedAndIndexEqualsValuesLength() {
        // Add mapping with index equal to values length
        mapping.put("key3", values.length);
        CSVRecord record = new CSVRecord(values, mapping, null, 1L);
        assertFalse(record.isSet("key3"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameMappedAndIndexGreaterThanValuesLength() {
        // Add mapping with index greater than values length
        mapping.put("key4", values.length + 1);
        CSVRecord record = new CSVRecord(values, mapping, null, 1L);
        assertFalse(record.isSet("key4"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameNotMapped() {
        assertFalse(csvRecord.isSet("notMappedKey"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nullName() {
        assertFalse(csvRecord.isSet(null));
    }

    @Test
    @Timeout(8000)
    void testIsSet_usingReflection_privateIsMapped() throws Exception {
        Method isMappedMethod = CSVRecord.class.getDeclaredMethod("isMapped", String.class);
        isMappedMethod.setAccessible(true);

        Boolean mappedTrue = (Boolean) isMappedMethod.invoke(csvRecord, "key0");
        assertTrue(mappedTrue);

        Boolean mappedFalse = (Boolean) isMappedMethod.invoke(csvRecord, "unknown");
        assertFalse(mappedFalse);

        Boolean mappedNull = (Boolean) isMappedMethod.invoke(csvRecord, (Object) null);
        assertFalse(mappedNull);
    }
}