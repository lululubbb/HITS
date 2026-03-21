package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_8_1Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;
    private String comment;
    private long recordNumber;

    @BeforeEach
    void setUp() {
        values = new String[] {"value1", "value2", "value3"};
        mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        mapping.put("col3", 2);
        comment = "comment";
        recordNumber = 42L;
        csvRecord = new CSVRecord(values, mapping, comment, recordNumber);
    }

    @Test
    @Timeout(8000)
    void testValuesMethod() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException {
        Method valuesMethod = CSVRecord.class.getDeclaredMethod("values");
        valuesMethod.setAccessible(true);
        String[] returnedValues = (String[]) valuesMethod.invoke(csvRecord);
        assertArrayEquals(values, returnedValues);

        // Test with empty values array
        CSVRecord emptyRecord = new CSVRecord(new String[0], Collections.emptyMap(), null, 0L);
        String[] emptyReturned = (String[]) valuesMethod.invoke(emptyRecord);
        assertNotNull(emptyReturned);
        assertEquals(0, emptyReturned.length);
    }
}