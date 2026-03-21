package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CSVRecord_8_3Test {

    @Test
    @Timeout(8000)
    void testValues() throws Exception {
        // Prepare test data
        String[] testValues = new String[] { "value1", "value2", "value3" };
        Map<String, Integer> testMapping = new HashMap<>();
        testMapping.put("col1", 0);
        testMapping.put("col2", 1);
        String testComment = "comment";
        long testRecordNumber = 123L;

        // Create instance of CSVRecord
        CSVRecord record = new CSVRecord(testValues, testMapping, testComment, testRecordNumber);

        // Use reflection to access package-private method values()
        Method valuesMethod = CSVRecord.class.getDeclaredMethod("values");
        valuesMethod.setAccessible(true);

        // Invoke the values() method
        String[] returnedValues = (String[]) valuesMethod.invoke(record);

        // Assert returned array is same as original
        assertArrayEquals(testValues, returnedValues);

        // Additional assertions to verify no side effects
        assertEquals(testComment, record.getComment());
        assertEquals(testRecordNumber, record.getRecordNumber());
        assertEquals(testValues.length, record.size());

        // Also test with empty values array
        CSVRecord emptyRecord = new CSVRecord(new String[0], Collections.emptyMap(), null, 0L);
        String[] emptyReturnedValues = (String[]) valuesMethod.invoke(emptyRecord);
        assertArrayEquals(new String[0], emptyReturnedValues);
    }
}